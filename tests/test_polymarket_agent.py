import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta


def _market(question, active=True, closed=False, minutes_from_now=3):
    end = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return {
        "condition_id": "0xabc",
        "question": question,
        "active": active,
        "closed": closed,
        "end_date_iso": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tokens": [
            {"token_id": "111", "outcome": "Yes", "price": 0.54, "winner": False},
            {"token_id": "222", "outcome": "No",  "price": 0.46, "winner": False},
        ],
    }



def test_get_token_ids_returns_up_down():
    from polymarket_agent import get_token_ids
    market = _market("Will BTC be higher in 5 min?")
    up_id, down_id = get_token_ids(market)
    assert up_id == "111"
    assert down_id == "222"


def test_get_token_ids_raises_if_missing():
    from polymarket_agent import get_token_ids
    market = {
        "condition_id": "0xabc",
        "tokens": [{"token_id": "111", "outcome": "Yes", "price": 0.54, "winner": False}],
    }
    try:
        get_token_ids(market)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_calc_avg_fill_price_single_trade():
    from polymarket_agent import calc_avg_fill_price
    trades = [{"price": "0.54", "size": "4.962"}]
    assert abs(calc_avg_fill_price(trades) - 0.54) < 0.0001


def test_calc_avg_fill_price_weighted():
    from polymarket_agent import calc_avg_fill_price
    # (0.50*2 + 0.60*3) / 5 = 0.56
    trades = [{"price": "0.50", "size": "2.0"}, {"price": "0.60", "size": "3.0"}]
    assert abs(calc_avg_fill_price(trades) - 0.56) < 0.0001


def test_calc_avg_fill_price_empty_returns_none():
    from polymarket_agent import calc_avg_fill_price
    assert calc_avg_fill_price([]) is None


def test_calc_pnl_win():
    from polymarket_agent import calc_pnl
    payout, pnl = calc_pnl(shares=4.962, cost=2.69, won=True)
    assert abs(payout - 4.962) < 0.001
    assert abs(pnl - 2.272) < 0.001


def test_calc_pnl_loss():
    from polymarket_agent import calc_pnl
    payout, pnl = calc_pnl(shares=4.962, cost=2.69, won=False)
    assert payout == 0.0
    assert abs(pnl - (-2.69)) < 0.001


def test_format_countdown_minutes_and_seconds():
    from polymarket_agent import format_countdown
    assert format_countdown(252) == "4m 12s"


def test_format_countdown_seconds_only():
    from polymarket_agent import format_countdown
    assert format_countdown(45) == "45s"


def test_format_countdown_zero():
    from polymarket_agent import format_countdown
    assert format_countdown(0) == "0s"


def test_format_countdown_negative():
    from polymarket_agent import format_countdown
    assert format_countdown(-5) == "0s"


def test_format_countdown_exact_minute():
    from polymarket_agent import format_countdown
    assert format_countdown(60) == "1m 0s"
