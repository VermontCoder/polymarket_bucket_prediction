import json
import time
import urllib.request
import urllib.parse


def fetch_url(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_post(url: str, body: bytes):
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_open_price_for_window(window_start: int, symbol: str = "BTCUSDT",
                                retries: int = 6, retry_delay: float = 2.0) -> float | None:
    """Return the 1-minute Binance open price at the given UTC epoch second.

    Retries up to `retries` times (2s apart) in case the kline hasn't appeared
    yet on Binance (e.g. when called right at or just before the window boundary).
    """
    start_ms = window_start * 1000
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={symbol}&interval=1m&startTime={start_ms}&limit=1")
    for _ in range(retries):
        data = fetch_url(url)
        if data and int(data[0][0]) == start_ms:
            return float(data[0][1])
        time.sleep(retry_delay)
    return None


def fetch_btc5m_snapshot(
    up_token_id: str,
    down_token_id: str,
    window_end_epoch: int,
) -> dict:
    """Fetch current CLOB order books + Binance spot price for the BTC-5m market.

    Returns dict with keys: up_ask, down_ask (cents, 0-100), current_price,
    time_to_close (ms, computed from wall clock vs window end).
    ask values are None if no asks in book.
    """
    body = json.dumps([
        {"token_id": up_token_id},
        {"token_id": down_token_id},
    ]).encode()
    books_list = fetch_post("https://clob.polymarket.com/books", body)
    books = {item["asset_id"]: item for item in books_list}

    encoded = urllib.parse.quote(json.dumps(["BTCUSDT"], separators=(",", ":")))
    price_data = fetch_url(f"https://api.binance.com/api/v3/ticker/price?symbols={encoded}")
    current_price = float(price_data[0]["price"]) if price_data else None

    def best_ask_cents(token_id: str) -> float | None:
        book = books.get(token_id, {})
        asks = book.get("asks", [])
        return float(asks[-1]["price"]) * 100 if asks else None

    time_to_close = max(0, window_end_epoch * 1000 - int(time.time() * 1000))

    return {
        "up_ask":        best_ask_cents(up_token_id),
        "down_ask":      best_ask_cents(down_token_id),
        "current_price": current_price,
        "time_to_close": time_to_close,
    }
