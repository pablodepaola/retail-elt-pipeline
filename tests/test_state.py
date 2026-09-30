import datetime as dt

from pipeline import state


def test_advance_is_monotonic():
    wm = state.Watermark(last_loaded_date="2018-01-05")
    state.advance(wm, dt.date(2018, 1, 3))  # earlier date must not move it back
    assert wm.last_loaded_date == "2018-01-05"
    state.advance(wm, dt.date(2018, 1, 10))
    assert wm.last_loaded_date == "2018-01-10"


def test_roundtrip(tmp_path):
    path = tmp_path / "wm.json"
    wm = state.Watermark(last_loaded_date="2018-02-01", runs=3)
    state.save_watermark(wm, path)
    loaded = state.load_watermark(path)
    assert loaded.last_loaded_date == "2018-02-01"
    assert loaded.runs == 3
    assert loaded.last_run_at is not None
