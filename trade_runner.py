from dataclasses import dataclass


@dataclass
class TradeResult:
    session_id:    str
    outcome:       str        # UP / DOWN
    direction:     str        # UP / DOWN — side with the higher ask
    correct:       bool       # direction == outcome
    row_timestamp: str
    bucket:        tuple
    ask_price:     float      # cents
    smoothed_rate: float      # 0.0–1.0
    shares_bought: float
    cost:          float      # dollars
    payout:        float      # dollars
    pnl:           float      # dollars


def calc_shares(ask_price: float) -> float:
    """Return shares purchasable for a 5-share budget after the Polymarket fee.

    ask_price: in cents (0–100).
    fee formula: 0.02 * price * (1 - price / 100)
    """
    fee_per_share = 0.02 * ask_price * (1 - ask_price / 100)
    budget = 5 * ask_price
    return budget / (ask_price + fee_per_share)


def get_row_signal(row, smoothed_rates: dict):
    """Return (direction, ask_price, bucket, smoothed_rate) if a trade signal fires, else None.

    Fires when smoothed_rate >= (dominant_ask + 10) / 100.
    dominant_ask = whichever of up_ask / down_ask is strictly higher.
    """
    if row.up_ask is None or row.down_ask is None:
        return None
    if row.up_ask == row.down_ask:
        return None

    if row.up_ask > row.down_ask:
        direction, ask_price = "UP", row.up_ask
    else:
        direction, ask_price = "DOWN", row.down_ask

    ttc = row.time_to_close
    if ttc < 0 or ttc > 300000:
        return None
    if row.diff_pct is None:
        return None

    x = ttc // 2000
    y = max(0, min(299, int(row.diff_pct * 300 + 150)))
    bucket = (x, y)

    if bucket not in smoothed_rates:
        return None

    smoothed_rate = smoothed_rates[bucket]
    if smoothed_rate >= (ask_price + 10) / 100:
        return direction, ask_price, bucket, smoothed_rate
    return None


def run_session(session, smoothed_rates: dict):
    """Iterate a session's rows in order; return a TradeResult for the first signal, or None."""
    for row in session.rows:
        signal = get_row_signal(row, smoothed_rates)
        if signal is None:
            continue
        direction, ask_price, bucket, smoothed_rate = signal
        shares = calc_shares(ask_price)
        cost = (5 * ask_price) / 100
        payout = shares * 1.0 if direction == session.outcome else 0.0
        return TradeResult(
            session_id=session.session_id,
            outcome=session.outcome,
            direction=direction,
            correct=(direction == session.outcome),
            row_timestamp=row.timestamp,
            bucket=bucket,
            ask_price=ask_price,
            smoothed_rate=smoothed_rate,
            shares_bought=shares,
            cost=cost,
            payout=payout,
            pnl=payout - cost,
        )
    return None
