import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
from market_data import fetch_open_price_for_window, fetch_5m_snapshot


def test_fetch_open_price_for_window_returns_float():
    window_start = 1775078400
    # Binance kline[0][0] is open time in ms; must match window_start * 1000 exactly
    kline_resp = [[window_start * 1000, "84000.50", "84100.00", "83900.00", "84050.00",
                   "10.5", 0, "0", 0, "0", "0", "0"]]
    with patch("market_data.fetch_url", return_value=kline_resp):
        price = fetch_open_price_for_window(window_start=window_start, symbol="BTCUSDT")
    assert price == 84000.50


def test_fetch_open_price_for_window_empty_returns_none():
    with patch("market_data.fetch_url", return_value=[]):
        price = fetch_open_price_for_window(window_start=1775078400, symbol="BTCUSDT")
    assert price is None


def test_fetch_5m_snapshot_returns_dict():
    books_resp = [
        {"asset_id": "UP_TOKEN", "bids": [{"price": "0.45"}], "asks": [{"price": "0.54"}], "timestamp": 1775078450000},
        {"asset_id": "DN_TOKEN", "bids": [{"price": "0.43"}], "asks": [{"price": "0.46"}], "timestamp": 1775078450000},
    ]
    price_resp = [{"symbol": "BTCUSDT", "price": "84100.00"}]
    with patch("market_data.fetch_post", return_value=books_resp), \
         patch("market_data.fetch_url", return_value=price_resp):
        snap = fetch_5m_snapshot("UP_TOKEN", "DN_TOKEN", window_end_epoch=1775078700)
    assert snap["up_ask"] == 54.0   # 0.54 * 100
    assert snap["down_ask"] == 46.0
    assert snap["current_price"] == 84100.0
    assert snap["time_to_close"] >= 0


def test_fetch_5m_snapshot_missing_book_returns_none_asks():
    books_resp = [
        {"asset_id": "UP_TOKEN", "bids": [], "asks": [], "timestamp": 1775078450000},
        {"asset_id": "DN_TOKEN", "bids": [], "asks": [], "timestamp": 1775078450000},
    ]
    price_resp = [{"symbol": "BTCUSDT", "price": "84100.00"}]
    with patch("market_data.fetch_post", return_value=books_resp), \
         patch("market_data.fetch_url", return_value=price_resp):
        snap = fetch_5m_snapshot("UP_TOKEN", "DN_TOKEN", window_end_epoch=1775078700)
    assert snap["up_ask"] is None
    assert snap["down_ask"] is None
