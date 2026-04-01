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


def _make_state(status, market=None, slug=None, fill=None):
    import threading
    from polymarket_agent import AppState
    return AppState(
        status=status,
        market=market,
        slug=slug,
        up_token_id="111",
        down_token_id="222",
        fill=fill,
        log_lines=[],
        lock=threading.Lock(),
    )



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


def test_appstate_log_appends():
    from polymarket_agent import AppState, Status
    import threading
    state = AppState(
        status=Status.WAITING_FOR_ORDER,
        market=None, slug=None,
        up_token_id=None, down_token_id=None,
        fill=None, log_lines=[],
        lock=threading.Lock(),
    )
    state.log("hello")
    state.log("world")
    assert state.log_lines == ["hello", "world"]


def test_appstate_log_caps_at_max():
    from polymarket_agent import AppState, Status, MAX_LOG_LINES
    import threading
    state = AppState(
        status=Status.WAITING_FOR_ORDER,
        market=None, slug=None,
        up_token_id=None, down_token_id=None,
        fill=None, log_lines=[],
        lock=threading.Lock(),
    )
    for i in range(MAX_LOG_LINES + 10):
        state.log(str(i))
    assert len(state.log_lines) == MAX_LOG_LINES
    assert state.log_lines[-1] == str(MAX_LOG_LINES + 9)


def test_build_left_panel_waiting_for_order_contains_menu():
    from polymarket_agent import build_left_panel, Status
    market = {"question": "Will BTC go up?"}
    state = _make_state(Status.WAITING_FOR_ORDER, market=market, slug="btc-updown-5m-123")
    panel = build_left_panel(state, seconds_remaining=42)
    text = panel.renderable if hasattr(panel, 'renderable') else str(panel)
    assert "Buy UP" in str(text)
    assert "Buy DOWN" in str(text)
    assert "Exit" in str(text)
    assert "42" in str(text)


def test_build_left_panel_order_placed_hides_buy_options():
    from polymarket_agent import build_left_panel, Status
    fill = {"side_label": "UP", "cost": 3.25, "shares": 5.0}
    market = {"question": "Will BTC go up?"}
    state = _make_state(Status.ORDER_PLACED, market=market, slug="btc-updown-5m-123", fill=fill)
    panel = build_left_panel(state, seconds_remaining=42)
    text = str(panel.renderable if hasattr(panel, 'renderable') else panel)
    assert "Buy UP" not in text
    assert "Buy DOWN" not in text
    assert "UP" in text  # fill side_label shown


def test_build_left_panel_waiting_next_market():
    from polymarket_agent import build_left_panel, Status
    state = _make_state(Status.WAITING_NEXT_MARKET)
    panel = build_left_panel(state, seconds_remaining=180)
    text = str(panel.renderable if hasattr(panel, 'renderable') else panel)
    assert "next market" in text.lower()


def test_build_right_panel_shows_log_lines():
    from polymarket_agent import build_right_panel, Status
    import threading
    from polymarket_agent import AppState
    state = AppState(
        status=Status.WAITING_FOR_ORDER,
        market=None, slug=None,
        up_token_id=None, down_token_id=None,
        fill=None,
        log_lines=["line one", "line two", "line three"],
        lock=threading.Lock(),
    )
    panel = build_right_panel(state, panel_height=20)
    text = str(panel.renderable if hasattr(panel, 'renderable') else panel)
    assert "line one" in text
    assert "line three" in text


def test_build_right_panel_truncates_to_height():
    from polymarket_agent import build_right_panel, Status
    import threading
    from polymarket_agent import AppState
    state = AppState(
        status=Status.WAITING_FOR_ORDER,
        market=None, slug=None,
        up_token_id=None, down_token_id=None,
        fill=None,
        log_lines=[f"line {i}" for i in range(50)],
        lock=threading.Lock(),
    )
    panel = build_right_panel(state, panel_height=5)
    text = str(panel.renderable if hasattr(panel, 'renderable') else panel)
    assert "line 49" in text   # newest line present
    assert "line 0" not in text  # oldest line trimmed
