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


def test_find_btc_5min_market_returns_nearest():
    from polymarket_agent import find_btc_5min_market
    m1 = _market("Will BTC be higher in 5 min?", minutes_from_now=10)
    m2 = _market("Will BTC be higher in 5 min?", minutes_from_now=3)
    result = find_btc_5min_market([m1, m2])
    assert result is m2


def test_find_btc_5min_market_ignores_inactive():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will BTC be higher in 5 min?", active=False)
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_ignores_closed():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will BTC be higher in 5 min?", closed=True)
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_ignores_non_btc():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will ETH be higher in 5 min?")
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_ignores_non_5min():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will BTC be higher at end of day?")
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_no_markets():
    from polymarket_agent import find_btc_5min_market
    assert find_btc_5min_market([]) is None


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
