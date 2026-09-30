from pipeline.contracts import CONTRACTS, validate_table


def _all_cols(table: str) -> list[str]:
    c = CONTRACTS[table]
    return list(c.required_columns) + list(c.optional_columns)


def test_good_columns_pass():
    assert validate_table("orders", _all_cols("orders")) == []


def test_missing_required_is_detected():
    problems = validate_table("orders", ["order_id"])
    assert any("missing required" in p for p in problems)


def test_unexpected_new_column_flags_drift():
    cols = _all_cols("orders") + ["surprise_column"]
    problems = validate_table("orders", cols)
    assert any("unexpected new columns" in p for p in problems)


def test_unregistered_table_is_noop():
    assert validate_table("not_a_table", ["whatever"]) == []
