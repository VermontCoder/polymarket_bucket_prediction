# trade_runner.py — Design Spec
**Date:** 2026-03-29

## Overview

A paper trading simulation that runs the smoothed bucket prediction model against the test dataset. For each test session, it scans rows in order, fires at most one trade per session when a signal threshold is met, then evaluates the outcome at session close. Results are logged per-trade and summarised at the end.

---

## Inputs

| Source | File |
|---|---|
| Smoothed bucket rates | `data/smoothed_rates.json` (loaded via existing `load_bucket_rates()` from `main.py`) |
| Test sessions | `data/btc_polymarket_combined_20260325_134508_test.json` (loaded via existing `load_sessions()` from `main.py`) |

---

## Signal Logic

For each session, iterate rows in chronological order. For each row:

1. **Skip** if `up_ask` or `down_ask` is `None`.
2. **Skip** if `up_ask == down_ask` (no dominant side, no signal).
3. Determine `direction` and `ask_price`:
   - `direction = "UP"`, `ask_price = up_ask` if `up_ask > down_ask`
   - `direction = "DOWN"`, `ask_price = down_ask` if `down_ask > up_ask`
4. Compute bucket `(x, y)` using the same formula as `Session.to_buckets()`:
   - Skip if `time_to_close` is `None`, `< 0`, or `> 300000`
   - Skip if `diff_pct` is `None`
   - `x = time_to_close // 2000`
   - `y = clamp(int(diff_pct * 300 + 150), 0, 299)`
5. **Skip** if bucket `(x, y)` is not present in smoothed rates.
6. **Take trade** if `smoothed_rate >= (ask_price + 10) / 100`. Stop iterating rows for this session.

Sessions where no row triggers a trade are counted in the summary as "no signal" but produce no `TradeResult`.

---

## Fee, Shares, and Payout

All prices in cents (0–100 range as stored in the data).

```
fee_per_share  = 0.02 * ask_price * (1 - ask_price / 100)   # cents
cost_cents     = 5 * ask_price                               # budget: 5 shares worth
shares_bought  = cost_cents / (ask_price + fee_per_share)    # slightly less than 5
cost_dollars   = cost_cents / 100

payout         = shares_bought * 1.00  if direction == session.outcome  else 0.0
pnl            = payout - cost_dollars
```

**Example** at `ask_price = 60¢`:
- `fee_per_share = 0.02 * 60 * (1 - 0.60) = 0.48¢`
- `shares_bought = 300 / 60.48 ≈ 4.960`
- `cost = $3.00`
- Win → payout = $4.96, P&L = **+$1.96**
- Lose → payout = $0.00, P&L = **-$3.00**

---

## Data Structure

```python
@dataclass
class TradeResult:
    session_id:    str
    outcome:       str        # UP / DOWN
    direction:     str        # UP / DOWN (side with higher ask)
    correct:       bool       # direction == outcome
    row_timestamp: str
    bucket:        tuple[int, int]
    ask_price:     float      # cents
    smoothed_rate: float      # 0.0–1.0
    shares_bought: float
    cost:          float      # dollars
    payout:        float      # dollars
    pnl:           float      # dollars
```

---

## Functions

| Function | Signature | Purpose |
|---|---|---|
| `calc_shares` | `(ask_price: float) -> float` | Apply fee formula, return shares bought |
| `get_row_signal` | `(row, smoothed_rates) -> tuple[str, float, tuple, float] \| None` | Return `(direction, ask_price, bucket, smoothed_rate)` if signal fires, else `None` |
| `run_session` | `(session, smoothed_rates) -> TradeResult \| None` | Iterate rows, return first `TradeResult` or `None` |
| `print_trade_log` | `(results: list[TradeResult]) -> None` | Print per-trade detail block |
| `print_summary` | `(results, total_sessions: int) -> None` | Print aggregate stats |
| `save_trade_log` | `(results, filepath: str) -> None` | Write log to file |

---

## Output Format

### Per-trade log (console + file)

```
Session: 2026-03-24T15:35:00Z  outcome=UP  traded=UP
  timestamp                      bucket        ask    smoothed%   shares   cost     payout   pnl
  ------------------------------------------------------------------------------------------------
  2026-03-24T15:36:51.989Z       (94, 160)     51.0   64.1%       4.974    $2.55    $4.97    +$2.42
```

### Summary (console only)

```
Sessions in test set:   412
Trades taken:           187  (45.4%)
  Correct (win):        112  (59.9%)
  Incorrect (loss):      75  (40.1%)
Total P&L:             +$84.32
Avg P&L per trade:      +$0.45
```

Log saved to: `data/trade_log.txt`

---

## File Layout

- **`trade_runner.py`** — new standalone script; imports `load_sessions` and `load_bucket_rates` from `main.py`
- No changes to existing files.
