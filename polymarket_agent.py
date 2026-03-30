import os
import time

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import MarketOrderArgs, OrderType, TradeParams
from py_clob_client.order_builder.constants import BUY
from datetime import datetime, timezone

HOST = "https://clob.polymarket.com"


def find_btc_5min_market(markets: list) -> dict | None:
    """Return the active BTC 5-min market with the nearest future end_date_iso, or None."""
    now = datetime.now(timezone.utc)
    candidates = []
    for m in markets:
        if not (m.get("active") and not m.get("closed")):
            continue
        q = m.get("question", "").lower()
        if not any(kw in q for kw in ("btc", "bitcoin")):
            continue
        if not any(kw in q for kw in ("5 min", "5-min", "5 minute")):
            continue
        try:
            end = datetime.fromisoformat(m["end_date_iso"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if end > now:
            candidates.append((end, m))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def get_token_ids(market: dict) -> tuple:
    """Return (up_token_id, down_token_id).

    UP = token with outcome 'Yes'. DOWN = token with outcome 'No'.
    Raises ValueError if either token is missing.
    """
    up_id = None
    down_id = None
    for token in market["tokens"]:
        if token["outcome"] == "Yes":
            if up_id is not None:
                raise ValueError(
                    f"Duplicate 'Yes' token in market: {market.get('condition_id')}"
                )
            up_id = token["token_id"]
        elif token["outcome"] == "No":
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
    chain_id_str = os.getenv("POLY_CHAIN_ID", "137")
    if not pk:
        raise EnvironmentError("POLY_PRIVATE_KEY not set in .env")
    chain_id = int(chain_id_str)
    client = ClobClient(HOST, key=pk, chain_id=chain_id)
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    return client


def fetch_all_markets(client: ClobClient) -> list:
    """Paginate get_markets() until end cursor, return all market dicts."""
    markets = []
    cursor = "MA=="
    while True:
        resp = client.get_markets(next_cursor=cursor)
        markets.extend(resp.get("data", []))
        cursor = resp.get("next_cursor", "LTE=")
        if cursor == "LTE=":
            break
    return markets


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


def poll_resolution(client: ClobClient, condition_id: str, fill: dict) -> None:
    """Poll for market resolution (up to 60s) and print win/loss result."""
    print()
    for _ in range(12):  # 12 × 5s = 60s max
        time.sleep(5)
        market = client.get_market(condition_id)
        if not market.get("closed"):
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


def main():
    try:
        client = build_client()
    except EnvironmentError as e:
        print(f"Error: {e}")
        return

    while True:
        print("\nLooking up active BTC 5-min market...")
        try:
            all_markets = fetch_all_markets(client)
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return

        market = find_btc_5min_market(all_markets)
        if market is None:
            print("No active BTC 5-minute market found. Exiting.")
            return

        condition_id = market["condition_id"]
        end_dt = datetime.fromisoformat(market["end_date_iso"].replace("Z", "+00:00"))
        up_token_id, down_token_id = get_token_ids(market)

        remaining = (end_dt - datetime.now(timezone.utc)).total_seconds()
        print(f"\nActive market: {market['question']}")
        print(f"Closes in: {format_countdown(int(remaining))}")
        print()
        print("1. Buy UP  (Yes)")
        print("2. Buy DOWN (No)")
        print("3. Exit")
        print()

        choice = input("Choice: ").strip()

        if choice == "3":
            print("Goodbye.")
            break
        elif choice == "1":
            selected_token_id, side_label = up_token_id, "UP"
        elif choice == "2":
            selected_token_id, side_label = down_token_id, "DOWN"
        else:
            print("Invalid choice — enter 1, 2, or 3.")
            continue

        try:
            fill = place_order(client, selected_token_id, side_label)
        except Exception as e:
            print(f"Order error: {e}")
            continue

        if fill is None:
            continue

        run_countdown(end_dt)

        try:
            poll_resolution(client, condition_id, fill)
        except Exception as e:
            print(f"Resolution error: {e}")


if __name__ == "__main__":
    main()
