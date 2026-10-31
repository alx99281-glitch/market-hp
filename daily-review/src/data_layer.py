"""データ層（SPEC_1.md フェーズ1）。

- 価格データはローカルに parquet で永続化する（ロング形式: date, ticker, ...）。
- 初回のみ過去N年分を一括取得。以降は毎回、直近数営業日を再取得して上書きする
  （取引時間中の値が確定値として残らないようにするため）。
- セッション未終了の当日バーは保存しない（cron遅延でザラ場中に走った場合の対策）。
- yf.download はチャンク単位のバッチリクエスト（銘柄ごとにループしない）。
  チャンク間に数秒のスリープ、失敗時は指数バックオフでリトライする。
- 第2ソースとして Stooq を用意し、yfinance が失敗した銘柄のみフォールバックする。
  注記: Stooq は現在ブラウザ確認(JS)による簡易ボット対策が入っており、
  単純なHTTPリクエストでは取得できない場合がある。失敗時は警告を出して
  「取得できなかった銘柄」として記録し、処理は継続する。
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from config import (
    DATA_DIR,
    INITIAL_HISTORY_YEARS,
    PRICE_STORE,
    REFRESH_LOOKBACK_DAYS,
    SESSION_SETTLE_MINUTES,
    YF_BACKOFF_BASE_SEC,
    YF_CHUNK_SIZE,
    YF_MAX_RETRIES,
    YF_SLEEP_SEC,
)

warnings.filterwarnings("ignore")

OHLCV_COLS = ["open", "high", "low", "close", "adj_close", "volume"]


@dataclass(frozen=True)
class MarketSession:
    """取引所のローカル時間帯と大引け時刻。当日バーの確定判定に使う。"""

    tz: str
    close: dt_time

    def unsettled_date(self) -> pd.Timestamp | None:
        """現在セッション未終了で、バーを保存してはいけない日付（なければNone）。"""
        now = pd.Timestamp.now(tz=self.tz)
        settled_at = now.normalize() + pd.Timedelta(
            hours=self.close.hour, minutes=self.close.minute + SESSION_SETTLE_MINUTES
        )
        return now.tz_localize(None).normalize() if now < settled_at else None


def _chunk(lst: list[str], size: int) -> list[list[str]]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def _wide_to_long(df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """yf.download(group_by='ticker')のワイド形式をロング形式に変換する。"""
    rows = []
    is_multi = isinstance(df.columns, pd.MultiIndex)
    for ticker in tickers:
        try:
            sub = df[ticker] if is_multi else df
        except KeyError:
            continue
        sub = sub.dropna(how="all")
        if sub.empty:
            continue
        sub = sub.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )
        sub = sub.reset_index().rename(columns={"Date": "date"})
        sub["ticker"] = ticker
        cols = ["date", "ticker"] + [c for c in OHLCV_COLS if c in sub.columns]
        rows.append(sub[cols])
    if not rows:
        return pd.DataFrame(columns=["date", "ticker"] + OHLCV_COLS)
    out = pd.concat(rows, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return out


def _download_chunk_with_retry(
    tickers: list[str], start: date, end: date, max_retries: int = YF_MAX_RETRIES
) -> pd.DataFrame:
    """1チャンクをyfinanceで取得。失敗時は指数バックオフでリトライする。

    start >= end（まだ当日データが存在しない等）の場合は「未確定なだけ」なので
    リトライせず即座に空を返す（本物の取得失敗と区別する）。
    """
    if start >= end:
        return pd.DataFrame(columns=["date", "ticker"] + OHLCV_COLS)

    last_err = None
    for attempt in range(max_retries):
        try:
            df = yf.download(
                tickers,
                start=start,
                end=end,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
            if df is None or df.empty:
                raise ValueError("empty response（対象期間に取引データがない可能性）")
            return _wide_to_long(df, tickers)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < max_retries - 1:
                wait = YF_BACKOFF_BASE_SEC * (2**attempt)
                print(f"  [warn] yfinance取得失敗 (attempt {attempt + 1}/{max_retries}): {e} -> {wait}秒待機")
                time.sleep(wait)
    print(f"  [warn] yfinanceチャンク取得を諦めました: {tickers[:5]}... ({last_err})")
    return pd.DataFrame(columns=["date", "ticker"] + OHLCV_COLS)


def _stooq_fallback(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Stooqの日次終値CSVを取得する（ベストエフォート、失敗時は空DataFrame）。"""
    symbol = ticker.lower().replace("^", "").replace("-", "-")
    # 米国株/ETFは `.us` サフィックスが必要
    stooq_symbol = symbol if "." in symbol else f"{symbol}.us"
    url = (
        f"https://stooq.com/q/d/l/?s={stooq_symbol}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
    )
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200 or "Date,Open,High,Low,Close,Volume" not in r.text[:100]:
            raise ValueError("Stooq応答がCSV形式ではない（ボット対策等でブロックされている可能性）")
        df = pd.read_csv(pd.io.common.StringIO(r.text))
        df = df.rename(columns={c: c.lower() for c in df.columns})
        df["date"] = pd.to_datetime(df["date"])
        df["ticker"] = ticker
        df["adj_close"] = df["close"]
        return df[["date", "ticker"] + OHLCV_COLS]
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] Stooqフォールバック失敗 ({ticker}): {e}")
        return pd.DataFrame(columns=["date", "ticker"] + OHLCV_COLS)


class MarketDataStore:
    """ロング形式parquetでの価格データ永続化ストア。"""

    def __init__(self, path=PRICE_STORE, session: MarketSession | None = None):
        self.path = path
        # None は24時間取引に近いマクロ系列用（当日バーも保存し、再取得で上書きする）
        self.session = session
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> pd.DataFrame:
        if self.path.exists():
            return pd.read_parquet(self.path)
        return pd.DataFrame(columns=["date", "ticker"] + OHLCV_COLS)

    def save(self, df: pd.DataFrame) -> None:
        # 再取得分が勝つよう、並べ替えの前に重複を除去する（sort_valuesは安定ソートではない）
        df = df.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
        df.to_parquet(self.path, index=False)

    def last_date_per_ticker(self) -> dict[str, pd.Timestamp]:
        df = self.load()
        if df.empty:
            return {}
        return df.groupby("ticker")["date"].max().to_dict()

    def _drop_unsettled(self, df: pd.DataFrame) -> pd.DataFrame:
        """終値のない行と、セッション未終了の当日バーを取り除く。"""
        df = df.dropna(subset=["close"])
        unsettled = self.session.unsettled_date() if self.session else None
        if unsettled is not None and (df["date"] == unsettled).any():
            print(f"  {unsettled.date()} はセッション未終了のため保存しません。")
            df = df[df["date"] != unsettled]
        return df

    def stored_tickers(self) -> set[str]:
        df = self.load()
        return set(df["ticker"].unique()) if not df.empty else set()

    def initial_bulk_fetch(self, tickers: list[str], years: int = INITIAL_HISTORY_YEARS) -> None:
        """未取得の銘柄について過去N年分を一括取得し、追記保存する。"""
        existing = self.stored_tickers()
        todo = [t for t in tickers if t not in existing]
        if not todo:
            print("初回一括取得: 対象銘柄はすべて取得済みです。")
            return

        end = date.today() + timedelta(days=1)
        start = end - timedelta(days=int(365.25 * years) + 5)

        print(f"初回一括取得: {len(todo)}銘柄 x {years}年分を{YF_CHUNK_SIZE}件ずつ取得します。")
        all_frames = []
        failed_tickers: list[str] = []
        chunks = _chunk(todo, YF_CHUNK_SIZE)
        for i, chunk in enumerate(chunks, 1):
            print(f"  chunk {i}/{len(chunks)} ({len(chunk)}銘柄)")
            long_df = _download_chunk_with_retry(chunk, start, end)
            got_tickers = set(long_df["ticker"].unique()) if not long_df.empty else set()
            missing = [t for t in chunk if t not in got_tickers]
            failed_tickers.extend(missing)
            all_frames.append(long_df)
            if i < len(chunks):
                time.sleep(YF_SLEEP_SEC)

        if failed_tickers:
            print(f"  yfinanceで取得できなかった{len(failed_tickers)}銘柄をStooqでフォールバック取得します。")
            for t in failed_tickers:
                fb = _stooq_fallback(t, start, end)
                if not fb.empty:
                    all_frames.append(fb)

        new_data = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
        if new_data.empty:
            print("  [error] 一括取得に失敗しました（データなし）。")
            return

        new_data = self._drop_unsettled(new_data)
        combined = pd.concat([self.load(), new_data], ignore_index=True)
        self.save(combined)
        got = set(new_data["ticker"].unique())
        still_missing = set(todo) - got
        print(f"初回一括取得完了: {len(got)}銘柄取得。未取得: {len(still_missing)}銘柄 {sorted(still_missing)[:20]}")

    def daily_update(self, tickers: list[str]) -> pd.DataFrame:
        """差分追記に加え、直近REFRESH_LOOKBACK_DAYS日分を再取得して上書きする。

        戻り値: 今回新規に追加された行（上書きされた既存行は含まない）。
        """
        last_dates = self.last_date_per_ticker()
        today = date.today()

        # 銘柄ごとに開始日が異なりうるが、yfinanceバッチのため
        # 「最も古い最終取得日」と再取得窓の早い方を基準にまとめて取得し、
        # 後で銘柄別に保存対象の行だけを残す。
        never_fetched = [t for t in tickers if t not in last_dates]
        already_fetched = [t for t in tickers if t in last_dates]

        fetched_frames = []

        if never_fetched:
            print(f"  {len(never_fetched)}銘柄は未取得のため初回一括取得を実行します。")
            self.initial_bulk_fetch(never_fetched)

        if already_fetched:
            refresh_start = today - timedelta(days=REFRESH_LOOKBACK_DAYS)
            oldest_last_date = min(last_dates[t] for t in already_fetched)
            start = min((oldest_last_date + timedelta(days=1)).date(), refresh_start)
            end = today + timedelta(days=1)
            chunks = _chunk(already_fetched, YF_CHUNK_SIZE)
            for i, chunk in enumerate(chunks, 1):
                long_df = _download_chunk_with_retry(chunk, start, end, max_retries=2)
                if not long_df.empty:
                    # 再取得窓の行と、銘柄ごとの既存最終日より後の行だけ残す
                    keep = (long_df["date"] >= pd.Timestamp(refresh_start)) | (
                        long_df["date"] > long_df["ticker"].map(last_dates)
                    )
                    fetched_frames.append(long_df[keep])
                if i < len(chunks):
                    time.sleep(YF_SLEEP_SEC)

        empty = pd.DataFrame(columns=["date", "ticker"] + OHLCV_COLS)
        if not fetched_frames:
            return empty
        fetched = self._drop_unsettled(pd.concat(fetched_frames, ignore_index=True))
        if fetched.empty:
            return empty

        existing = self.load()
        key = ["ticker", "date"]
        old_close = existing.set_index(key)["close"]
        new_close = fetched.set_index(key)["close"]
        common = new_close.index.intersection(old_close.index)
        revised = int((new_close.loc[common] - old_close.loc[common]).abs().gt(1e-6).sum())

        self.save(pd.concat([existing, fetched], ignore_index=True))
        new_rows = fetched[fetched["date"] > fetched["ticker"].map(last_dates)]
        print(f"  差分追記: {len(new_rows)}行を追加、既存{revised}行の終値を更新しました。")
        return new_rows

    def wide_close(self, tickers: list[str] | None = None) -> pd.DataFrame:
        """日付 x 銘柄 の終値(close)ワイド形式を返す（分析用）。"""
        df = self.load()
        if tickers is not None:
            df = df[df["ticker"].isin(tickers)]
        pivot = df.pivot_table(index="date", columns="ticker", values="close")
        return pivot.sort_index()
