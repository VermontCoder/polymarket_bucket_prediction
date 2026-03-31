import ast
import os
import time

import requests
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, TradeParams
from py_clob_client.order_builder.constants import BUY
from datetime import datetime, timezone

HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


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


def _fetch_gamma_market(slug: str) -> dict | None:
    """Query Gamma API for an event by slug and return its first market dict, or None if not found."""
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
    return markets[0] if markets else None


def _fetch_gamma_condition_id(slug: str) -> str | None:
    """Return the condition_id for a slug, or None if not found."""
    market = _fetch_gamma_market(slug)
    return market.get("conditionId") if market else None


def find_active_btc_5min_market(client: ClobClient) -> tuple[dict, str] | None:
    """Look up the current BTC 5-min market by computing its slug from the clock.

    Slug format: btc-updown-5m-{epoch} where epoch is the UTC timestamp of the
    start of the current 5-minute window (floored to nearest 300 seconds).
    Returns (clob_market_dict, slug), or None if not found or not yet active.
    """
    now = datetime.now(timezone.utc)
    window_start = (int(now.timestamp()) // 300) * 300
    slug = f"btc-updown-5m-{window_start}"

    condition_id = _fetch_gamma_condition_id(slug)
    if not condition_id:
        return None

    market: dict = client.get_market(condition_id)  # type: ignore[assignment]
    if not (market.get("active") and not market.get("closed")):
        return None
    return market, slug


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


def place_order(client: ClobClient, token_id: str, side_label: str) -> dict | None:
    """Place a limit buy for 5 shares at price 0.99. Prints fill details. Returns fill dict or None on failure.

    Returns dict with keys: order_id, token_id, side_label, shares, cost
    """
    order_args = OrderArgs(
        token_id=token_id,
        price=0.99,
        size=5.0,
        side=BUY,
    )
    signed = client.create_order(order_args)
    try:
        resp = client.post_order(signed, orderType=OrderType.FOK)  # type: ignore[arg-type]
    except Exception as e:
        print(f"Order placement failed: {e}")
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


def poll_resolution(slug: str, fill: dict) -> None:
    """Poll for market resolution (up to 60s) and print win/loss result.

    Rebuilds the client each iteration to avoid cached responses, and re-queries
    the Gamma API for a fresh condition_id before fetching market state.
    """
    print()
    for _ in range(50):  # 50 × 5s = 250s max
        time.sleep(5)
        fresh_client = build_client()
        order: dict = fresh_client.get_order(fill["order_id"])  # type: ignore[assignment]
        if order.get("expiration") != '0':
            print("Market not yet closed — waiting...")
            continue

        gamma_market = _fetch_gamma_market(slug)
        if not gamma_market:
            print("Could not retrieve market data from Gamma — retrying...")
            continue

        outcomes = ast.literal_eval(gamma_market.get("outcomes")) #Convert to array from string. 
        outcome_prices = ast.literal_eval(gamma_market.get("outcomePrices"))
        if len(outcomes) != len(outcome_prices):
            print("Malformed outcome data from Gamma — retrying...")
            continue

        resolved_label = None
        for outcome, price in zip(outcomes, outcome_prices):
            if float(price) == 1.0:
                resolved_label = outcome
                break

        if resolved_label is None:
            print("Resolution Pending.....")
            continue

        won = (order.get("outcome") == resolved_label)
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
