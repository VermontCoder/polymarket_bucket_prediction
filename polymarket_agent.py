import os
import sys
import time

import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType, TradeParams
from py_clob_client.order_builder.constants import BUY
from datetime import datetime, timezone

HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


def get_token_ids(market: dict) -> tuple:
    """Return (up_token_id, down_token_id).

    Raises ValueError if either token is missing.
    """
    up_id = None
    down_id = None
    for token in market["tokens"]:
        if token["outcome"] == "Up":
            if up_id is not None:
                raise ValueError(
                    f"Duplicate 'Yes' token in market: {market.get('condition_id')}"
                )
            up_id = token["token_id"]
        elif token["outcome"] == "Down":
            if down_id is not None:
                raise ValueError(
                    f"Duplicate 'No' token in market: {market.get('condition_id')}"
                )
            down_id = token["token_id"]
    if up_id is None or down_id is None:
        raise ValueError(
            f"Could not find Yes/No tokens in market: {market.get('condition_id')}"
        )
    return up_id, down_id


def calc_avg_fill_price(trades: list) -> float | None:
    """Return weighted average fill price from trade records, or None if no trades."""
    total_size = sum(float(t["size"]) for t in trades)
    if total_size == 0:
        return None
    return sum(float(t["price"]) * float(t["size"]) for t in trades) / total_size


def calc_pnl(shares: float, cost: float, won: bool) -> tuple:
    """Return (payout, pnl). Payout is $1.00/share if won, else $0."""
    payout = shares * 1.0 if won else 0.0
    return payout, payout - cost


def format_countdown(seconds: int) -> str:
    """Format seconds as 'Xm Ys' or 'Xs'. Returns '0s' for zero or negative."""
    if seconds <= 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def build_client() -> ClobClient:
    """Load credentials from .env, derive API creds, return fully authenticated ClobClient."""
    load_dotenv()
    pk = os.getenv("POLY_PRIVATE_KEY")
    pfa = os.getenv("POLYMARKET_FUNDER_ADDRESS")
    chain_id_str = os.getenv("POLY_CHAIN_ID", "137")
    if not pk:
        raise EnvironmentError("POLY_PRIVATE_KEY not set in .env")
    chain_id = int(chain_id_str)
    client = ClobClient(HOST, key=pk, chain_id=chain_id, signature_type=1, funder=pfa)
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    return client


def find_active_btc_5min_market(client: ClobClient) -> dict | None:
    """Look up the current BTC 5-min market by computing its slug from the clock.

    Slug format: btc-updown-5m-{epoch} where epoch is the UTC timestamp of the
    start of the current 5-minute window (floored to nearest 300 seconds).
    Returns the CLOB market dict, or None if not found or not yet active.
    """
    now = datetime.now(timezone.utc)
    window_start = (int(now.timestamp()) // 300) * 300
    slug = f"btc-updown-5m-{window_start}"

    resp = requests.get(f"{GAMMA_API}/events", params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # API returns [] when not found, [{event}] or a single {event} when found
    if isinstance(data, list):
        if not data:
            return None
        event = data[0]
    else:
        if not data:
            return None
        event = data

    markets = event.get("markets", [])
    if not markets:
        return None
    condition_id = markets[0].get("conditionId")
    if not condition_id:
        return None

    market: dict = client.get_market(condition_id)  # type: ignore[assignment]
    if not (market.get("active") and not market.get("closed")):
        return None
    return market


def run_countdown(end_dt) -> None:
    """Display a live single-line countdown to end_dt, updating every second."""
    while True:
        remaining = (end_dt - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            print("\rWaiting for market close...  [ closed ]              ", flush=True)
            break
        label = format_countdown(int(remaining))
        print(f"\rWaiting for market close...  [ {label} remaining ]   ", end="", flush=True)
        time.sleep(1)


def place_order(client: ClobClient, token_id: str, side_label: str) -> dict | None:
    """Place a $5 USDC market buy. Prints fill details. Returns fill dict or None on failure.

    Returns dict with keys: order_id, token_id, side_label, shares, cost
    """
    order_args = MarketOrderArgs(
        token_id=token_id,
        price=.99,
        amount=5.0,
        side=BUY,
        order_type=OrderType.FOK,
    )
    signed = client.create_market_order(order_args)
    resp = client.post_order(signed, orderType=OrderType.FOK)

    if not resp.get("success"):
        print(f"Order failed: {resp.get('errorMsg', 'unknown error')}")
        return None

    order_id = resp["orderID"]
    print(f"\nOrder placed: BUY {side_label}")
    print(f"  Order ID:   {order_id}")

    time.sleep(2)
    order = client.get_order(order_id)
    size_matched = float(order.get("size_matched", "0"))

    if size_matched == 0:
        print("  Order not filled.")
        return None

    trades_resp = client.get_trades(TradeParams(asset_id=token_id))
    # get_trades returns a list or a dict with 'data' key depending on version
    trades = trades_resp if isinstance(trades_resp, list) else trades_resp.get("data", [])
    avg_price = calc_avg_fill_price(trades)
    cost = size_matched * avg_price if avg_price else size_matched * 0.5

    print(f"  Shares:     {size_matched:.3f}")
    if avg_price:
        print(f"  Avg price:  ${avg_price:.3f}")
    print(f"  Cost:       ${cost:.2f}")

    return {
        "order_id": order_id,
        "token_id": token_id,
        "side_label": side_label,
        "shares": size_matched,
        "cost": cost,
    }


def poll_resolution( client: ClobClient, condition_id: str, fill: dict) -> None:
    """Poll for market resolution (up to 60s) and print win/loss result."""
    print()
    for _ in range(12):  # 12 × 5s = 60s max
        time.sleep(5)
        market = client.get_market(condition_id)
        if not market.get("closed"):
            print(market)
            continue

        winning_token_id = None
        resolved_label = None
        for token in market["tokens"]:
            if token.get("winner"):
                winning_token_id = token["token_id"]
                resolved_label = "UP" if token["outcome"] == "Yes" else "DOWN"
                break

        if winning_token_id is None:
            print("Resolution unclear — check Polymarket.")
            return

        won = (winning_token_id == fill["token_id"])
        payout, pnl = calc_pnl(fill["shares"], fill["cost"], won)
        result = "WIN " if won else "LOSS"
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

        print(f"Result: {result} — bought {fill['side_label']}, resolved {resolved_label}")
        print(
            f"  Shares: {fill['shares']:.3f}  |  "
            f"Paid: ${fill['cost']:.2f}  |  "
            f"Payout: ${payout:.2f}  |  "
            f"P&L: {pnl_str}"
        )
        return

    print(f"\nResolution pending — check Polymarket for order {fill['order_id']}")

def seconds_until_next_five_min_interval():
    """
    Calculates the number of seconds from a given timestamp to the next 
    five-minute interval boundary (e.g., hh:00:00, hh:05:00, ..., hh:55:00).
    
    Args:
        now_timestamp: The current time, typically from datetime.now()
    
    Returns:
        The number of seconds (float) until the next five-minute interval.
    """
    
    # Calculate the total seconds from the epoch to the current time
    # using time.time() is efficient for this purpose
    timestamp = time.time()
    
    # The next 5-minute interval in seconds since the epoch is found 
    # by adding 300 seconds to the current timestamp and then using 
    # the modulo operator to find the remainder, which is subtracted
    # from the current time plus 300 seconds.
    interval_seconds = 300 # 5 minutes * 60 seconds/minute
    
    # The time of the next interval mark (since epoch)
    next_interval_timestamp = timestamp + interval_seconds - (timestamp % interval_seconds)
    
    # The difference is the time remaining
    seconds_remaining = next_interval_timestamp - timestamp
    
    # Alternatively, you can use datetime objects for clarity and the total_seconds() method:
    # now = datetime.fromtimestamp(timestamp)
    # next_interval = datetime.fromtimestamp(next_interval_timestamp)
    # seconds_remaining_dt = (next_interval - now).total_seconds()
    
    return seconds_remaining // 1

def main():
    try:
        client = build_client()
    except EnvironmentError as e:
        print(f"Error: {e}")
        return

    print("\nLooking up active BTC 5-min market...")
    try:
        market = find_active_btc_5min_market(client)
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return
    if market is None:
        print("No active BTC 5-minute market found. Exiting.")
        return

    condition_id = market["condition_id"]
    print(f"Found active market with condition ID: {condition_id}")
    up_token_id, down_token_id = get_token_ids(market)

    remaining = seconds_until_next_five_min_interval()
    print(f"\nActive market: {market['question']}")
    print(f"Closes in: {remaining:.0f} seconds")
    print()
    print("1. Buy UP  (Yes)")
    print("2. Buy DOWN (No)")
    print("3. Exit")
    print()

    choice = input("Choice: ").strip()

    if choice == "3":
        print("Goodbye.")
        sys.exit(1)
    elif choice == "1":
        selected_token_id, side_label = up_token_id, "UP"
    elif choice == "2":
        selected_token_id, side_label = down_token_id, "DOWN"
    else:
        print("Invalid choice — enter 1, 2, or 3.")
        sys.exit(1)
    
    try:
        fill = place_order(client, selected_token_id, side_label)
    except Exception as e:
        print(f"Order error: {e}")
        sys.exit(1)

    if fill is None:
        print("No fill obtained. Exiting.")
        sys.exit(1)

    print("\nOrder filled. Waiting for market to close...")

    remaining = seconds_until_next_five_min_interval()
    time.sleep(int(remaining))

    print("\nMarket closed. Checking resolution...")

    try:
        poll_resolution( client, condition_id ,fill)
    except Exception as e:
        print(f"Resolution error: {e}")


if __name__ == "__main__":
    main()
