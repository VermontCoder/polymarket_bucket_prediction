import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_runner import TradeResult


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
