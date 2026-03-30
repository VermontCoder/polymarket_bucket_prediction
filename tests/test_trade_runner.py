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
