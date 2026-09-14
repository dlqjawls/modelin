"""Small process independent cache for successfully downloaded OHLCV frames."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pandas as pd


class PersistentOHLCVCache:
    """Persist non-empty daily frames so worker restarts do not redownload them."""

    def __init__(self, root: str, source: str):
        self.root = Path(root) / source
        self._memory: dict[tuple[str, str], pd.DataFrame] = {}

    def _path(self, symbol: str, interval: str) -> Path:
        key = "|".join((symbol, interval)).encode("utf-8")
        return self.root / f"{hashlib.sha256(key).hexdigest()}.pkl"

    def get(self, symbol: str, start: str, end: str, interval: str) -> pd.DataFrame | None:
        path = self._path(symbol, interval)
        key = (symbol, interval)
        frame = self._memory.get(key)
        if frame is None and path.is_file():
            try:
                frame = pd.read_pickle(path)
                if isinstance(frame, pd.DataFrame) and not frame.empty:
                    self._memory[key] = frame
            except Exception:
                frame = None
        if frame is None:
            return None
        try:
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                return None
            index = pd.to_datetime(frame.index).tz_localize(None)
            requested_start = pd.Timestamp(start)
            requested_end = pd.Timestamp(end)
            if index.min() > requested_start or index.max() < requested_end:
                return None
            result = frame.copy()
            result.index = index
            return result.loc[(result.index >= requested_start) & (result.index <= requested_end)]
        except Exception:
            # A partial write or an old incompatible cache must never block data.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def set(self, symbol: str, start: str, end: str, interval: str, frame: pd.DataFrame) -> None:
        if frame is None or frame.empty:
            return
        path = self._path(symbol, interval)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        try:
            try:
                previous = pd.read_pickle(path) if path.is_file() else None
                if not isinstance(previous, pd.DataFrame) or previous.empty:
                    previous = None
            except Exception:
                previous = None
            merged = pd.concat([previous, frame]) if previous is not None else frame
            merged = merged[~pd.Index(merged.index).duplicated(keep="last")].sort_index()
            merged.to_pickle(temporary)
            os.replace(temporary, path)
            self._memory[(symbol, interval)] = merged
        finally:
            temporary.unlink(missing_ok=True)
