from dataclasses import dataclass

from main import load_sessions, load_bucket_rates


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


def _format_trade_log(results: list) -> str:
    header = f"  {'timestamp':<30} {'bucket':<14} {'ask':>5}  {'smoothed%':>9}  {'shares':>7}  {'cost':>7}  {'payout':>7}  {'pnl':>8}"
    divider = f"  {'-' * 99}"
    lines = []
    for r in results:
        pnl_str = f"+${r.pnl:.2f}" if r.pnl >= 0 else f"-${abs(r.pnl):.2f}"
        cost_str = f"${r.cost:.2f}"
        payout_str = f"${r.payout:.2f}"
        lines.append(f"Session: {r.session_id}  outcome={r.outcome}  traded={r.direction}")
        lines.append(header)
        lines.append(divider)
        lines.append(
            f"  {r.row_timestamp:<30} {str(r.bucket):<14} {r.ask_price:>5.1f}"
            f"  {r.smoothed_rate * 100:>8.1f}%  {r.shares_bought:>7.3f}"
            f"  {cost_str:>7}  {payout_str:>7}  {pnl_str:>8}"
        )
        lines.append("")
    return "\n".join(lines)


def print_trade_log(results: list) -> None:
    print(_format_trade_log(results))


def save_trade_log(results: list, filepath: str) -> None:
    with open(filepath, "w") as f:
        f.write(_format_trade_log(results))


def print_summary(results: list, total_sessions: int) -> None:
    trades = len(results)
    wins = sum(1 for r in results if r.correct)
    losses = trades - wins
    total_pnl = sum(r.pnl for r in results)
    avg_pnl = total_pnl / trades if trades > 0 else 0.0
    trade_pct = trades / total_sessions * 100 if total_sessions > 0 else 0.0
    win_pct = wins / trades * 100 if trades > 0 else 0.0
    loss_pct = losses / trades * 100 if trades > 0 else 0.0
    pnl_str = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"
    avg_str = f"+${avg_pnl:.2f}" if avg_pnl >= 0 else f"-${abs(avg_pnl):.2f}"

    print(f"Sessions in test set:  {total_sessions}")
    print(f"Trades taken:          {trades}  ({trade_pct:.1f}%)")
    print(f"  Correct (win):       {wins}  ({win_pct:.1f}%)")
    print(f"  Incorrect (loss):    {losses}  ({loss_pct:.1f}%)")
    print(f"Total P&L:             {pnl_str}")
    print(f"Avg P&L per trade:     {avg_str}")


TEST_DATA = "data/btc_polymarket_combined_20260325_134508_test.json"
SMOOTHED_RATES_CACHE = "data/smoothed_rates.json"
TRADE_LOG_PATH = "data/trade_log.txt"

if __name__ == "__main__":
    smoothed_rates = load_bucket_rates(SMOOTHED_RATES_CACHE)
    sessions = load_sessions(TEST_DATA)
    print(f"Test sessions loaded:  {len(sessions)}")
    print()

    results = []
    for session in sessions:
        result = run_session(session, smoothed_rates)
        if result is not None:
            results.append(result)

    print_trade_log(results)
    save_trade_log(results, TRADE_LOG_PATH)
    print(f"Trade log saved to {TRADE_LOG_PATH}")
    print()
    print_summary(results, total_sessions=len(sessions))
