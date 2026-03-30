# trade_runner.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a paper trading simulation that runs the smoothed bucket model against the test dataset and reports per-trade results and summary P&L stats.

**Architecture:** A single `trade_runner.py` script with a `TradeResult` dataclass, four pure functions (`calc_shares`, `get_row_signal`, `run_session`), two output functions (`print_trade_log`, `save_trade_log`), one stats function (`print_summary`), and a `__main__` block. It imports `load_sessions` and `load_bucket_rates` from the existing `main.py`. A `tests/test_trade_runner.py` file covers all logic via TDD.

**Tech Stack:** Python 3.10+, dataclasses, pytest

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `trade_runner.py` | All trading logic, output formatting, main entry point |
| Create | `tests/test_trade_runner.py` | Unit tests for all functions |

No existing files are modified.

---

### Task 1: TradeResult dataclass

**Files:**
- Create: `trade_runner.py`
- Create: `tests/test_trade_runner.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_trade_runner.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_runner import TradeResult


def test_trade_result_fields():
    r = TradeResult(
        session_id="2026-03-24T15:35:00Z",
        outcome="UP",
        direction="UP",
        correct=True,
        row_timestamp="2026-03-24T15:36:51.989Z",
        bucket=(94, 160),
        ask_price=51.0,
        smoothed_rate=0.641,
        shares_bought=4.974,
        cost=2.55,
        payout=4.97,
        pnl=2.42,
    )
    assert r.session_id == "2026-03-24T15:35:00Z"
    assert r.correct is True
    assert r.pnl == 2.42
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_trade_runner.py::test_trade_result_fields -v
```
Expected: `ImportError` — `trade_runner` not found.

- [ ] **Step 3: Create `trade_runner.py` with the dataclass**

```python
# trade_runner.py
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
```

- [ ] **Step 4: Run test to confirm it passes**

```
pytest tests/test_trade_runner.py::test_trade_result_fields -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trade_runner.py tests/test_trade_runner.py
git commit -m "feat: add TradeResult dataclass and test scaffold"
```

---

### Task 2: calc_shares

**Files:**
- Modify: `trade_runner.py` — add `calc_shares`
- Modify: `tests/test_trade_runner.py` — add tests

- [ ] **Step 1: Add the tests**

Append to `tests/test_trade_runner.py`:

```python
from trade_runner import calc_shares


def test_calc_shares_mid_price():
    # ask=60: fee = 0.02*60*(1-60/100) = 0.48, budget=300, shares=300/60.48
    expected = 300 / 60.48
    assert abs(calc_shares(60.0) - expected) < 0.001


def test_calc_shares_high_price():
    # ask=90: fee = 0.02*90*(1-90/100) = 0.18, budget=450, shares=450/90.18
    expected = 450 / 90.18
    assert abs(calc_shares(90.0) - expected) < 0.001


def test_calc_shares_low_price():
    # ask=10: fee = 0.02*10*(1-10/100) = 0.18, budget=50, shares=50/10.18
    expected = 50 / 10.18
    assert abs(calc_shares(10.0) - expected) < 0.001
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_trade_runner.py -k "calc_shares" -v
```
Expected: `ImportError` — `calc_shares` not found.

- [ ] **Step 3: Implement `calc_shares` in `trade_runner.py`**

Add after the dataclass:

```python
def calc_shares(ask_price: float) -> float:
    """Return shares purchasable for a 5-share budget after the Polymarket fee.

    ask_price: in cents (0–100).
    fee formula: 0.02 * price * (1 - price / 100)
    """
    fee_per_share = 0.02 * ask_price * (1 - ask_price / 100)
    budget = 5 * ask_price
    return budget / (ask_price + fee_per_share)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_trade_runner.py -k "calc_shares" -v
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add trade_runner.py tests/test_trade_runner.py
git commit -m "feat: add calc_shares with fee formula"
```

---

### Task 3: get_row_signal

**Files:**
- Modify: `trade_runner.py` — add `get_row_signal`
- Modify: `tests/test_trade_runner.py` — add tests

- [ ] **Step 1: Add the tests**

Append to `tests/test_trade_runner.py`:

```python
from row import Row
from trade_runner import get_row_signal


def _row(up_ask, down_ask, diff_pct, time_to_close, timestamp="2026-01-01T00:00:00Z"):
    """Build a Row from keyword args for test convenience."""
    return Row({
        "timestamp": timestamp,
        "up_bid": None, "up_ask": up_ask,
        "down_bid": None, "down_ask": down_ask,
        "current_price": 50.0,
        "diff_pct": diff_pct, "diff_usd": None,
        "time_to_close": time_to_close,
    })


def test_signal_fires_up():
    # up_ask=70 > down_ask=30 → UP; bucket x=60, y=180; threshold=(70+10)/100=0.80; rate=0.82 ≥ 0.80
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    result = get_row_signal(row, {(60, 180): 0.82})
    assert result is not None
    direction, ask, bucket, rate = result
    assert direction == "UP"
    assert ask == 70.0
    assert bucket == (60, 180)
    assert rate == 0.82


def test_signal_fires_down():
    # down_ask=65 > up_ask=35 → DOWN; x=50, y=clamp(int(-0.05*300+150))=135; threshold=0.75; rate=0.76 ≥ 0.75
    row = _row(up_ask=35.0, down_ask=65.0, diff_pct=-0.05, time_to_close=100000)
    result = get_row_signal(row, {(50, 135): 0.76})
    assert result is not None
    direction, ask, bucket, rate = result
    assert direction == "DOWN"
    assert ask == 65.0
    assert bucket == (50, 135)


def test_signal_below_threshold():
    # threshold=0.80, rate=0.79 → no signal
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.79}) is None


def test_signal_at_threshold():
    # rate == threshold exactly → fires (>=)
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.80}) is not None


def test_signal_null_up_ask():
    row = _row(up_ask=None, down_ask=60.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {}) is None


def test_signal_null_down_ask():
    row = _row(up_ask=60.0, down_ask=None, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {}) is None


def test_signal_equal_asks():
    row = _row(up_ask=50.0, down_ask=50.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.99}) is None


def test_signal_bucket_not_in_rates():
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=120000)
    assert get_row_signal(row, {}) is None


def test_signal_null_diff_pct():
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=None, time_to_close=120000)
    assert get_row_signal(row, {(60, 180): 0.99}) is None


def test_signal_ttc_too_large():
    # time_to_close=400000 > 300000 → skip
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=400000)
    assert get_row_signal(row, {(200, 180): 0.99}) is None


def test_signal_ttc_negative():
    # time_to_close=-1 < 0 → skip
    row = _row(up_ask=70.0, down_ask=30.0, diff_pct=0.1, time_to_close=-1)
    assert get_row_signal(row, {}) is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_trade_runner.py -k "signal" -v
```
Expected: `ImportError` — `get_row_signal` not found.

- [ ] **Step 3: Implement `get_row_signal` in `trade_runner.py`**

Add after `calc_shares`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_trade_runner.py -k "signal" -v
```
Expected: 12 PASS

- [ ] **Step 5: Commit**

```bash
git add trade_runner.py tests/test_trade_runner.py
git commit -m "feat: add get_row_signal with bucket threshold logic"
```

---

### Task 4: run_session

**Files:**
- Modify: `trade_runner.py` — add `run_session`
- Modify: `tests/test_trade_runner.py` — add tests

- [ ] **Step 1: Add the tests**

Append to `tests/test_trade_runner.py`:

```python
from session import Session
from trade_runner import run_session


def _row_dict(up_ask, down_ask, diff_pct, time_to_close, timestamp="2026-01-01T00:00:00Z"):
    return {
        "timestamp": timestamp,
        "up_bid": None, "up_ask": up_ask,
        "down_bid": None, "down_ask": down_ask,
        "current_price": 50.0,
        "diff_pct": diff_pct, "diff_usd": None,
        "time_to_close": time_to_close,
    }


def _session(outcome, rows_dicts):
    return Session({
        "session_id": "test-session",
        "outcome": outcome,
        "hour": 12, "day": 1,
        "diff_pct_prev_session": None,
        "diff_pct_hour": None,
        "avg_pct_variance_hour": None,
        "rows": rows_dicts,
    })


def test_run_session_returns_trade_result():
    # up_ask=70, bucket=(60,180), rate=0.82, threshold=0.80 → fires
    s = _session("UP", [_row_dict(70.0, 30.0, 0.1, 120000)])
    result = run_session(s, {(60, 180): 0.82})
    assert result is not None
    assert result.direction == "UP"
    assert result.outcome == "UP"
    assert result.correct is True
    assert result.bucket == (60, 180)
    assert result.ask_price == 70.0


def test_run_session_correct_pnl():
    # cost = 5*70/100 = $3.50; shares = calc_shares(70); payout = shares*1.00
    s = _session("UP", [_row_dict(70.0, 30.0, 0.1, 120000)])
    result = run_session(s, {(60, 180): 0.82})
    fee = 0.02 * 70 * (1 - 70 / 100)
    expected_shares = 350 / (70 + fee)
    assert abs(result.shares_bought - expected_shares) < 0.001
    assert abs(result.cost - 3.50) < 0.001
    assert abs(result.payout - expected_shares) < 0.001
    assert abs(result.pnl - (expected_shares - 3.50)) < 0.001


def test_run_session_incorrect_pnl():
    # direction=UP but outcome=DOWN → payout=0, pnl=-(cost)
    s = _session("DOWN", [_row_dict(70.0, 30.0, 0.1, 120000)])
    result = run_session(s, {(60, 180): 0.82})
    assert result.correct is False
    assert result.payout == 0.0
    assert abs(result.pnl - (-3.50)) < 0.001


def test_run_session_no_signal_returns_none():
    # rate=0.75 < threshold=0.80 → no trade
    s = _session("UP", [_row_dict(70.0, 30.0, 0.1, 120000)])
    assert run_session(s, {(60, 180): 0.75}) is None


def test_run_session_stops_at_first_trade():
    # Two rows both eligible — only the first should be taken
    row1 = _row_dict(70.0, 30.0, 0.1, 120000, timestamp="2026-01-01T00:00:01Z")
    row2 = _row_dict(80.0, 20.0, 0.2, 100000, timestamp="2026-01-01T00:00:02Z")
    s = _session("UP", [row1, row2])
    # row1: bucket (60,180) threshold=0.80; row2: bucket (50,210) threshold=0.90
    rates = {(60, 180): 0.82, (50, 210): 0.95}
    result = run_session(s, rates)
    assert result.row_timestamp == "2026-01-01T00:00:01Z"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_trade_runner.py -k "run_session" -v
```
Expected: `ImportError` — `run_session` not found.

- [ ] **Step 3: Implement `run_session` in `trade_runner.py`**

Add after `get_row_signal`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_trade_runner.py -k "run_session" -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add trade_runner.py tests/test_trade_runner.py
git commit -m "feat: add run_session — first-signal trade per session"
```

---

### Task 5: print_trade_log and save_trade_log

**Files:**
- Modify: `trade_runner.py` — add `_format_trade_log`, `print_trade_log`, `save_trade_log`
- Modify: `tests/test_trade_runner.py` — add tests

- [ ] **Step 1: Add the tests**

Append to `tests/test_trade_runner.py`:

```python
from trade_runner import print_trade_log, save_trade_log


def _sample_result(correct=True):
    cost = 2.55
    payout = 4.97 if correct else 0.0
    return TradeResult(
        session_id="2026-03-24T15:35:00Z",
        outcome="UP", direction="UP", correct=correct,
        row_timestamp="2026-03-24T15:36:51.989Z",
        bucket=(94, 160), ask_price=51.0, smoothed_rate=0.641,
        shares_bought=4.974, cost=cost, payout=payout, pnl=payout - cost,
    )


def test_print_trade_log_contains_key_fields(capsys):
    print_trade_log([_sample_result()])
    out = capsys.readouterr().out
    assert "outcome=UP" in out
    assert "traded=UP" in out
    assert "2026-03-24T15:36:51.989Z" in out
    assert "(94, 160)" in out


def test_print_trade_log_negative_pnl(capsys):
    print_trade_log([_sample_result(correct=False)])
    out = capsys.readouterr().out
    assert "-$" in out


def test_save_trade_log_writes_file(tmp_path):
    filepath = str(tmp_path / "trade_log.txt")
    save_trade_log([_sample_result()], filepath)
    with open(filepath) as f:
        content = f.read()
    assert "outcome=UP" in content
    assert "2026-03-24T15:36:51.989Z" in content
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_trade_runner.py -k "trade_log" -v
```
Expected: `ImportError` — `print_trade_log` not found.

- [ ] **Step 3: Implement the output functions in `trade_runner.py`**

Add after `run_session`:

```python
def _format_trade_log(results: list) -> str:
    header = f"  {'timestamp':<30} {'bucket':<14} {'ask':>5}  {'smoothed%':>9}  {'shares':>7}  {'cost':>7}  {'payout':>7}  {'pnl':>8}"
    divider = f"  {'-' * 94}"
    lines = []
    for r in results:
        pnl_str = f"+${r.pnl:.2f}" if r.pnl >= 0 else f"-${abs(r.pnl):.2f}"
        lines.append(f"Session: {r.session_id}  outcome={r.outcome}  traded={r.direction}")
        lines.append(header)
        lines.append(divider)
        lines.append(
            f"  {r.row_timestamp:<30} {str(r.bucket):<14} {r.ask_price:>5.1f}"
            f"  {r.smoothed_rate * 100:>8.1f}%  {r.shares_bought:>7.3f}"
            f"  ${r.cost:.2f}  ${r.payout:.2f}  {pnl_str:>8}"
        )
        lines.append("")
    return "\n".join(lines)


def print_trade_log(results: list) -> None:
    print(_format_trade_log(results))


def save_trade_log(results: list, filepath: str) -> None:
    with open(filepath, "w") as f:
        f.write(_format_trade_log(results))
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_trade_runner.py -k "trade_log" -v
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add trade_runner.py tests/test_trade_runner.py
git commit -m "feat: add print_trade_log and save_trade_log output functions"
```

---

### Task 6: print_summary

**Files:**
- Modify: `trade_runner.py` — add `print_summary`
- Modify: `tests/test_trade_runner.py` — add tests

- [ ] **Step 1: Add the tests**

Append to `tests/test_trade_runner.py`:

```python
from trade_runner import print_summary


def test_print_summary_counts(capsys):
    results = [_sample_result(correct=True), _sample_result(correct=False)]
    print_summary(results, total_sessions=10)
    out = capsys.readouterr().out
    assert "10" in out           # total sessions
    assert "2  (20.0%)" in out   # trades taken out of 10
    assert "1  (50.0%)" in out   # wins out of 2


def test_print_summary_pnl(capsys):
    results = [_sample_result(correct=True)]   # pnl = 4.97 - 2.55 = +$2.42
    print_summary(results, total_sessions=5)
    out = capsys.readouterr().out
    assert "+$" in out


def test_print_summary_no_trades(capsys):
    print_summary([], total_sessions=10)
    out = capsys.readouterr().out
    assert "Trades taken:          0" in out
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_trade_runner.py -k "summary" -v
```
Expected: `ImportError` — `print_summary` not found.

- [ ] **Step 3: Implement `print_summary` in `trade_runner.py`**

Add after `save_trade_log`:

```python
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
```

- [ ] **Step 4: Run all tests to confirm everything passes**

```
pytest tests/test_trade_runner.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add trade_runner.py tests/test_trade_runner.py
git commit -m "feat: add print_summary with win rate and P&L stats"
```

---

### Task 7: Main block

**Files:**
- Modify: `trade_runner.py` — add imports and `__main__` block

- [ ] **Step 1: Add the imports and main block to `trade_runner.py`**

At the top of `trade_runner.py`, after the existing `from dataclasses import dataclass` line, add:

```python
from main import load_sessions, load_bucket_rates
```

At the bottom of `trade_runner.py`, add:

```python
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
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```
pytest tests/test_trade_runner.py -v
```
Expected: all tests PASS

- [ ] **Step 3: Run the script and verify output**

```
python trade_runner.py
```
Expected output format:
```
Test sessions loaded:  <N>

Session: <session_id>  outcome=<UP/DOWN>  traded=<UP/DOWN>
  timestamp                      bucket         ask  smoothed%    shares     cost   payout      pnl
  ----------------------------------------------------------------------------------------------
  <timestamp>                    (<x>, <y>)    <ask>  <rate>%    <shares>  $<cost>  $<pay>  +/-$<pnl>

...

Trade log saved to data/trade_log.txt

Sessions in test set:  <N>
Trades taken:          <T>  (<pct>%)
  Correct (win):       <W>  (<pct>%)
  Incorrect (loss):    <L>  (<pct>%)
Total P&L:             +/-$<pnl>
Avg P&L per trade:     +/-$<pnl>
```

- [ ] **Step 4: Commit**

```bash
git add trade_runner.py
git commit -m "feat: add trade_runner main block — paper trades test set"
```
