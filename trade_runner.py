import random
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


def get_row_signal(row, smoothed_rates: dict, threshold: float = 10):
    """Return (direction, ask_price, bucket, effective_rate) if a trade signal fires, else None.

    Two signals are checked per row:
    - Primary:    smoothed_rate        >= (dominant_ask + threshold) / 100  → buy dominant side
    - Contrarian: (1 - smoothed_rate)  >= (minority_ask  + threshold) / 100  → buy minority side

    If both fire, the one with the larger margin above its threshold is taken.
    If margins are equal, the choice is random.
    effective_rate returned is smoothed_rate for primary, (1 - smoothed_rate) for contrarian.
    """
    if row.up_ask is None or row.down_ask is None:
        return None
    if row.up_ask == row.down_ask:
        return None

    if row.up_ask > row.down_ask:
        dominant_dir, dominant_ask = "UP", row.up_ask
        minority_dir, minority_ask = "DOWN", row.down_ask
    else:
        dominant_dir, dominant_ask = "DOWN", row.down_ask
        minority_dir, minority_ask = "UP", row.up_ask

    ttc = row.time_to_close
    if ttc is None or ttc < 0 or ttc > 300000:
        return None
    if row.diff_pct is None:
        return None

    x = ttc // 2000
    y = max(0, min(299, int(row.diff_pct * 300 + 150)))
    bucket = (x, y)

    if bucket not in smoothed_rates:
        return None

    smoothed_rate = smoothed_rates[bucket]
    contrarian_rate = 1.0 - smoothed_rate

    primary_margin = smoothed_rate - (dominant_ask + threshold) / 100
    contrarian_margin = contrarian_rate - (minority_ask + threshold) / 100

    primary_fires = primary_margin >= 0
    contrarian_fires = contrarian_margin >= 0

    if not primary_fires and not contrarian_fires:
        return None

    if primary_fires and not contrarian_fires:
        return dominant_dir, dominant_ask, bucket, smoothed_rate

    if contrarian_fires and not primary_fires:
        return minority_dir, minority_ask, bucket, contrarian_rate

    # Both fire: take the larger margin; break ties randomly
    if primary_margin > contrarian_margin:
        return dominant_dir, dominant_ask, bucket, smoothed_rate
    elif contrarian_margin > primary_margin:
        return minority_dir, minority_ask, bucket, contrarian_rate
    else:
        if random.random() < 0.5:
            return dominant_dir, dominant_ask, bucket, smoothed_rate
        return minority_dir, minority_ask, bucket, contrarian_rate


def run_session(session, smoothed_rates: dict, threshold: float = 10):
    """Iterate a session's rows in order; return a TradeResult for the first signal, or None."""
    for row in session.rows:
        signal = get_row_signal(row, smoothed_rates, threshold)
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


def _run_all(sessions: list, smoothed_rates: dict, threshold: float) -> list:
    results = []
    for session in sessions:
        result = run_session(session, smoothed_rates, threshold)
        if result is not None:
            results.append(result)
    return results


def print_sweep_table(train_sessions: list, test_sessions: list, smoothed_rates: dict) -> None:
    """Run thresholds 5–15 over both datasets and print a summary table."""
    col = 14  # column width for each metric cell
    header = (
        f"{'':>12} | "
        f"{'--- TRAIN ---':^{col * 3 + 4}} | "
        f"{'--- TEST ---':^{col * 3 + 4}}"
    )
    subheader = (
        f"{'Threshold':>12} | "
        f"{'Trades':>{col}} {'Win%':>{col}} {'Total P&L':>{col}} | "
        f"{'Trades':>{col}} {'Win%':>{col}} {'Total P&L':>{col}}"
    )
    divider = "-" * len(subheader)

    print(header)
    print(subheader)
    print(divider)

    for t in range(5, 16):
        train_r = _run_all(train_sessions, smoothed_rates, t)
        test_r = _run_all(test_sessions, smoothed_rates, t)

        def stats(results, total):
            trades = len(results)
            wins = sum(1 for r in results if r.correct)
            pnl = sum(r.pnl for r in results)
            win_pct = wins / trades * 100 if trades > 0 else 0.0
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            return f"{trades:>{col}} {win_pct:>{col-1}.1f}% {pnl_str:>{col}}"

        label = f"+{t}%"
        print(
            f"{label:>12} | "
            f"{stats(train_r, len(train_sessions))} | "
            f"{stats(test_r, len(test_sessions))}"
        )


TRAIN_DATA = "data/btc_polymarket_combined_20260325_134508_train.json"
TEST_DATA = "data/btc_polymarket_combined_20260325_134508_test.json"
SMOOTHED_RATES_CACHE = "data/smoothed_rates.json"
TRADE_LOG_PATH = "data/trade_log.txt"

if __name__ == "__main__":
    import sys
    smoothed_rates = load_bucket_rates(SMOOTHED_RATES_CACHE)

    if "--sweep" in sys.argv:
        print("Loading train and test sessions...")
        train_sessions = load_sessions(TRAIN_DATA)
        test_sessions = load_sessions(TEST_DATA)
        print(f"Train: {len(train_sessions)} sessions  |  Test: {len(test_sessions)} sessions")
        print()
        print_sweep_table(train_sessions, test_sessions, smoothed_rates)
    else:
        sessions = load_sessions(TEST_DATA)
        print(f"Test sessions loaded:  {len(sessions)}")
        print()

        results = _run_all(sessions, smoothed_rates, threshold=10)

        print_trade_log(results)
        save_trade_log(results, TRADE_LOG_PATH)
        print(f"Trade log saved to {TRADE_LOG_PATH}")
        print()
        print_summary(results, total_sessions=len(sessions))
