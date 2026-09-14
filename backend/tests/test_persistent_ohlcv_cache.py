import pandas as pd

from data.persistent_ohlcv_cache import PersistentOHLCVCache


def test_persistent_cache_round_trips_non_empty_frame(tmp_path):
    cache = PersistentOHLCVCache(str(tmp_path), "krx")
    frame = pd.DataFrame({"open": [1], "high": [2], "low": [1], "close": [2], "volume": [10]})
    cache.set("005930", "2025-01-01", "2025-01-31", "1d", frame)
    loaded = cache.get("005930", "2025-01-01", "2025-01-31", "1d")
    pd.testing.assert_frame_equal(loaded, frame)


def test_persistent_cache_does_not_store_empty_frames(tmp_path):
    cache = PersistentOHLCVCache(str(tmp_path), "krx")
    cache.set("missing", "2025-01-01", "2025-01-31", "1d", pd.DataFrame())
    assert cache.get("missing", "2025-01-01", "2025-01-31", "1d") is None


def test_persistent_cache_covers_a_later_request_without_replacing_history(tmp_path):
    cache = PersistentOHLCVCache(str(tmp_path), "krx")
    first = pd.DataFrame({"close": [1, 2]}, index=pd.to_datetime(["2025-01-01", "2025-01-02"]))
    second = pd.DataFrame({"close": [3]}, index=pd.to_datetime(["2025-01-03"]))
    cache.set("x", "2025-01-01", "2025-01-02", "1d", first)
    cache.set("x", "2025-01-03", "2025-01-03", "1d", second)
    loaded = cache.get("x", "2025-01-01", "2025-01-03", "1d")
    assert list(loaded["close"]) == [1, 2, 3]
