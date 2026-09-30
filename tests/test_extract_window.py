import datetime as dt

from pipeline import extract
from pipeline.state import Watermark


def test_window_starts_after_watermark():
    wm = Watermark(last_loaded_date="2018-01-03")
    days = extract.plan_window(wm, use_sample=True, start=None, end=None, max_days=2)
    assert days[0] == dt.date(2018, 1, 4)
    assert len(days) <= 2


def test_window_empty_when_caught_up():
    wm = Watermark(last_loaded_date="2030-01-01")
    assert extract.plan_window(wm, use_sample=True, start=None, end=None) == []


def test_explicit_backfill_range_is_clamped_to_source():
    wm = Watermark()
    days = extract.plan_window(
        wm, use_sample=True, start=dt.date(1990, 1, 1), end=dt.date(2018, 1, 2)
    )
    # clamped to the sample's earliest available date, not 1990
    assert days[0] >= dt.date(2018, 1, 1)
    assert days[-1] == dt.date(2018, 1, 2)
