from jiffy_metrics import bars, ms, pct, table


def test_ms_keeps_three_significant_digits() -> None:
    assert ms(0.00123) == "1.23 ms"
    assert ms(0.0456) == "45.6 ms"
    assert ms(0.2261) == "226 ms"


def test_pct() -> None:
    assert pct(0.5) == "50.0%"
    assert pct(0.0077) == "0.77%"
    assert pct(0) == "0.0%"


def test_table_columns_line_up() -> None:
    lines = table(["a", "long header"], [[1, 2], ["wide cell", 3]]).splitlines()
    assert len({len(line) for line in lines}) == 1
    assert lines[1].startswith("|--")


def test_bars_scale_to_the_largest() -> None:
    out = bars(["a", "bb"], [1.0, 2.0], width=10).splitlines()
    assert out[0] == " a | ##### 1.0"
    assert out[1] == "bb | ########## 2.0"
