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


from session import Session
from trade_runner import run_session


def _row_dict(up_ask, down_ask, diff_pct, time_to_close, timestamp="2026-01-01T00:00:00Z"):
    return {
        "timestamp": timestamp,
        "up_bid": None, "up_ask": up_ask,
        "down_bid": None, "down_ask": down_ask,
        "current_price": 50.0,
        "diff_pct": diff_pct, "diff_usd": None,
        "time_to_close": time_to_close,
    }


def _session(outcome, rows_dicts):
    return Session({
        "session_id": "test-session",
        "outcome": outcome,
        "hour": 12, "day": 1,
        "diff_pct_prev_session": None,
        "diff_pct_hour": None,
        "avg_pct_variance_hour": None,
        "rows": rows_dicts,
    })


def test_run_session_returns_trade_result():
    # up_ask=70, bucket=(60,180), rate=0.82, threshold=0.80 → fires
    s = _session("UP", [_row_dict(70.0, 30.0, 0.1, 120000)])
    result = run_session(s, {(60, 180): 0.82})
    assert result is not None
    assert result.direction == "UP"
    assert result.outcome == "UP"
    assert result.correct is True
    assert result.bucket == (60, 180)
    assert result.ask_price == 70.0


def test_run_session_correct_pnl():
    # cost = 5*70/100 = $3.50; shares = calc_shares(70); payout = shares*1.00
    s = _session("UP", [_row_dict(70.0, 30.0, 0.1, 120000)])
    result = run_session(s, {(60, 180): 0.82})
    fee = 0.02 * 70 * (1 - 70 / 100)
    expected_shares = 350 / (70 + fee)
    assert abs(result.shares_bought - expected_shares) < 0.001
    assert abs(result.cost - 3.50) < 0.001
    assert abs(result.payout - expected_shares) < 0.001
    assert abs(result.pnl - (expected_shares - 3.50)) < 0.001


def test_run_session_incorrect_pnl():
    # direction=UP but outcome=DOWN → payout=0, pnl=-(cost)
    s = _session("DOWN", [_row_dict(70.0, 30.0, 0.1, 120000)])
    result = run_session(s, {(60, 180): 0.82})
    assert result.correct is False
    assert result.payout == 0.0
    assert abs(result.pnl - (-3.50)) < 0.001


def test_run_session_no_signal_returns_none():
    # rate=0.75 < threshold=0.80 → no trade
    s = _session("UP", [_row_dict(70.0, 30.0, 0.1, 120000)])
    assert run_session(s, {(60, 180): 0.75}) is None


def test_run_session_stops_at_first_trade():
    # Two rows both eligible — only the first should be taken
    row1 = _row_dict(70.0, 30.0, 0.1, 120000, timestamp="2026-01-01T00:00:01Z")
    row2 = _row_dict(80.0, 20.0, 0.2, 100000, timestamp="2026-01-01T00:00:02Z")
    s = _session("UP", [row1, row2])
    # row1: bucket (60,180) threshold=0.80; row2: bucket (50,210) threshold=0.90
    rates = {(60, 180): 0.82, (50, 210): 0.95}
    result = run_session(s, rates)
    assert result.row_timestamp == "2026-01-01T00:00:01Z"


from trade_runner import print_trade_log, save_trade_log


def _sample_result(correct=True):
    cost = 2.55
    payout = 4.97 if correct else 0.0
    return TradeResult(
        session_id="2026-03-24T15:35:00Z",
        outcome="UP", direction="UP", correct=correct,
        row_timestamp="2026-03-24T15:36:51.989Z",
        bucket=(94, 160), ask_price=51.0, smoothed_rate=0.641,
        shares_bought=4.974, cost=cost, payout=payout, pnl=payout - cost,
    )


def test_print_trade_log_contains_key_fields(capsys):
    print_trade_log([_sample_result()])
    out = capsys.readouterr().out
    assert "outcome=UP" in out
    assert "traded=UP" in out
    assert "2026-03-24T15:36:51.989Z" in out
    assert "(94, 160)" in out


def test_print_trade_log_negative_pnl(capsys):
    print_trade_log([_sample_result(correct=False)])
    out = capsys.readouterr().out
    assert "-$" in out


def test_save_trade_log_writes_file(tmp_path):
    filepath = str(tmp_path / "trade_log.txt")
    save_trade_log([_sample_result()], filepath)
    with open(filepath) as f:
        content = f.read()
    assert "outcome=UP" in content
    assert "2026-03-24T15:36:51.989Z" in content
