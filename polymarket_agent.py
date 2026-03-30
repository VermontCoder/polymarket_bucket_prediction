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
