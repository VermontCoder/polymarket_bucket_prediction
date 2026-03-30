import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_runner import TradeResult, calc_shares


def test_trade_result_fields():
    r = TradeResult(
        session_id="2026-03-24T15:35:00Z",
        outcome="UP",
        direction="UP",
        correct=True,
        row_timestamp="2026-03-24T15:36:51.989Z",
        bucket=(94, 160),
        ask_price=51.0,
        smoothed_rate=0.641,
        shares_bought=4.974,
        cost=2.55,
        payout=4.97,
        pnl=2.42,
    )
    assert r.session_id == "2026-03-24T15:35:00Z"
    assert r.correct is True
    assert r.pnl == 2.42


def test_calc_shares_mid_price():
    # ask=60: fee = 0.02*60*(1-60/100) = 0.48, budget=300, shares=300/60.48
    expected = 300 / 60.48
    assert abs(calc_shares(60.0) - expected) < 0.001


def test_calc_shares_high_price():
    # ask=90: fee = 0.02*90*(1-90/100) = 0.18, budget=450, shares=450/90.18
    expected = 450 / 90.18
    assert abs(calc_shares(90.0) - expected) < 0.001


def test_calc_shares_low_price():
    # ask=10: fee = 0.02*10*(1-10/100) = 0.18, budget=50, shares=50/10.18
    expected = 50 / 10.18
    assert abs(calc_shares(10.0) - expected) < 0.001


from row import Row
from trade_runner import get_row_signal


def _row(up_ask, down_ask, diff_pct, time_to_close, timestamp="2026-01-01T00:00:00Z"):
    """Build a Row from keyword args for test convenience."""
    return Row({
        "timestamp": timestamp,
        "up_bid": None, "up_ask": up_ask,
        "down_bid": None, "down_ask": down_ask,
        "current_price": 50.0,
        "diff_pct": diff_pct, "diff_usd": None,
        "time_to_close": time_to_close,
    })


def test_signal_fires_up():
    # up_ask=70 > down_ask=30 → UP; bucket x=60, y=180; threshold=(70+10)/100=0.80; rate=0.82 ≥ 0.80
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    result = get_row_signal(row, {(60, 180): 0.82})
    assert result is not None
    direction, ask, bucket, rate = result
    assert direction == "UP"
    assert ask == 70.0
    assert bucket == (60, 180)
    assert rate == 0.82


def test_signal_fires_down():
    # down_ask=65 > up_ask=35 → DOWN; x=50, y=clamp(int(-0.05*300+150))=135; threshold=0.75; rate=0.76 ≥ 0.75
    row = _row(up_ask=35.0, down_ask=65.0, diff_pct=-0.05, time_to_close=100000)
    result = get_row_signal(row, {(50, 135): 0.76})
    assert result is not None
    direction, ask, bucket, rate = result
    assert direction == "DOWN"
    assert ask == 65.0
    assert bucket == (50, 135)


def test_signal_below_threshold():
    # threshold=0.80, rate=0.79 → no signal
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.79}) is None


def test_signal_at_threshold():
    # rate == threshold exactly → fires (>=)
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.80}) is not None


def test_signal_null_up_ask():
    row = _row(up_ask=None, down_ask=60.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {}) is None


def test_signal_null_down_ask():
    row = _row(up_ask=60.0, down_ask=None, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {}) is None


def test_signal_equal_asks():
    row = _row(up_ask=50.0, down_ask=50.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.99}) is None


def test_signal_bucket_not_in_rates():
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {}) is None


def test_signal_null_diff_pct():
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=None, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.99}) is None


def test_signal_ttc_too_large():
    # time_to_close=400000 > 300000 → skip
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=400000)
    assert get_row_signal(row, {}) is None


def test_signal_ttc_negative():
    # time_to_close=-1 < 0 → skip
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=-1)
    assert get_row_signal(row, {}) is None
