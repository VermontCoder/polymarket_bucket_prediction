# Polymarket Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `polymarket_agent.py`, a console script that places real $5 market buy orders on Polymarket's active 5-minute BTC UP/DOWN market, shows fill details, counts down to close, and reports profit or loss.

**Architecture:** Single standalone file `polymarket_agent.py`. Pure helper functions (market lookup, fill price, countdown formatter, P&L) are unit-tested. Network-dependent functions (auth, pagination, order placement, resolution polling) are manually tested against the live API. No imports from `trade_runner.py` or `main.py`.

**Tech Stack:** `py-clob-client`, `python-dotenv`, Python 3.11+, pytest

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `polymarket_agent.py` | Create | All agent logic |
| `tests/test_polymarket_agent.py` | Create | Unit tests for pure helpers |
| `requirements.txt` | Create | Pin `py-clob-client` and `python-dotenv` |
| `.gitignore` | Modify | Add `.env` |
| `.env` | Create (not committed) | `POLY_PRIVATE_KEY` and `POLY_CHAIN_ID` |

---

## Task 1: Env Setup

**Files:**
- Modify: `.gitignore`
- Create: `requirements.txt`

- [ ] **Step 1: Add `.env` to `.gitignore`**

Open `.gitignore` and add:

```
/data
__pycache__/
*.pyc
.env
```

- [ ] **Step 2: Create `requirements.txt`**

```
py-clob-client
python-dotenv
```

- [ ] **Step 3: Install dependencies**

Run:
```bash
pip install py-clob-client python-dotenv
```

Expected: installs without errors.

- [ ] **Step 4: Verify `.env` exists with credentials**

Ensure `c:\Users\dfelc\Documents\Code_Archive\polymarket\polymarket_bucket_predictor\.env` contains:
```
POLY_PRIVATE_KEY=0x<your_64_char_hex>
POLY_CHAIN_ID=137
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt
git commit -m "chore: add requirements.txt and gitignore .env"
```

---

## Task 2: Pure Helpers — Market Lookup

**Files:**
- Create: `polymarket_agent.py`
- Create: `tests/test_polymarket_agent.py`

These two functions take raw data structures and return results — no network calls, fully testable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_polymarket_agent.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta


def _market(question, active=True, closed=False, minutes_from_now=3):
    end = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return {
        "condition_id": "0xabc",
        "question": question,
        "active": active,
        "closed": closed,
        "end_date_iso": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tokens": [
            {"token_id": "111", "outcome": "Yes", "price": 0.54, "winner": False},
            {"token_id": "222", "outcome": "No",  "price": 0.46, "winner": False},
        ],
    }


def test_find_btc_5min_market_returns_nearest():
    from polymarket_agent import find_btc_5min_market
    m1 = _market("Will BTC be higher in 5 min?", minutes_from_now=10)
    m2 = _market("Will BTC be higher in 5 min?", minutes_from_now=3)
    result = find_btc_5min_market([m1, m2])
    assert result is m2


def test_find_btc_5min_market_ignores_inactive():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will BTC be higher in 5 min?", active=False)
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_ignores_closed():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will BTC be higher in 5 min?", closed=True)
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_ignores_non_btc():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will ETH be higher in 5 min?")
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_ignores_non_5min():
    from polymarket_agent import find_btc_5min_market
    m = _market("Will BTC be higher at end of day?")
    assert find_btc_5min_market([m]) is None


def test_find_btc_5min_market_no_markets():
    from polymarket_agent import find_btc_5min_market
    assert find_btc_5min_market([]) is None


def test_get_token_ids_returns_up_down():
    from polymarket_agent import get_token_ids
    market = _market("Will BTC be higher in 5 min?")
    up_id, down_id = get_token_ids(market)
    assert up_id == "111"
    assert down_id == "222"


def test_get_token_ids_raises_if_missing():
    from polymarket_agent import get_token_ids
    market = {
        "condition_id": "0xabc",
        "tokens": [{"token_id": "111", "outcome": "Yes", "price": 0.54, "winner": False}],
    }
    try:
        get_token_ids(market)
        assert False, "Expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_polymarket_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'polymarket_agent'`

- [ ] **Step 3: Create `polymarket_agent.py` with the two functions**

```python
from datetime import datetime, timezone


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
        end = datetime.fromisoformat(m["end_date_iso"].replace("Z", "+00:00"))
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
            up_id = token["token_id"]
        elif token["outcome"] == "No":
            down_id = token["token_id"]
    if up_id is None or down_id is None:
        raise ValueError(
            f"Could not find Yes/No tokens in market: {market.get('condition_id')}"
        )
    return up_id, down_id
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_polymarket_agent.py -v
```

Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
git add polymarket_agent.py tests/test_polymarket_agent.py
git commit -m "feat: add find_btc_5min_market and get_token_ids helpers"
```

---

## Task 3: Pure Helpers — Fill Price & P&L

**Files:**
- Modify: `polymarket_agent.py`
- Modify: `tests/test_polymarket_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polymarket_agent.py`:

```python
def test_calc_avg_fill_price_single_trade():
    from polymarket_agent import calc_avg_fill_price
    trades = [{"price": "0.54", "size": "4.962"}]
    assert abs(calc_avg_fill_price(trades) - 0.54) < 0.0001


def test_calc_avg_fill_price_weighted():
    from polymarket_agent import calc_avg_fill_price
    # (0.50*2 + 0.60*3) / 5 = 0.56
    trades = [{"price": "0.50", "size": "2.0"}, {"price": "0.60", "size": "3.0"}]
    assert abs(calc_avg_fill_price(trades) - 0.56) < 0.0001


def test_calc_avg_fill_price_empty_returns_none():
    from polymarket_agent import calc_avg_fill_price
    assert calc_avg_fill_price([]) is None


def test_calc_pnl_win():
    from polymarket_agent import calc_pnl
    payout, pnl = calc_pnl(shares=4.962, cost=2.69, won=True)
    assert abs(payout - 4.962) < 0.001
    assert abs(pnl - 2.272) < 0.001


def test_calc_pnl_loss():
    from polymarket_agent import calc_pnl
    payout, pnl = calc_pnl(shares=4.962, cost=2.69, won=False)
    assert payout == 0.0
    assert abs(pnl - (-2.69)) < 0.001
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_polymarket_agent.py::test_calc_avg_fill_price_single_trade -v
```

Expected: `ImportError: cannot import name 'calc_avg_fill_price'`

- [ ] **Step 3: Add functions to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_polymarket_agent.py -v
```

Expected: 14 PASSED

- [ ] **Step 5: Commit**

```bash
git add polymarket_agent.py tests/test_polymarket_agent.py
git commit -m "feat: add calc_avg_fill_price and calc_pnl helpers"
```

---

## Task 4: Pure Helper — Countdown Formatter

**Files:**
- Modify: `polymarket_agent.py`
- Modify: `tests/test_polymarket_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_polymarket_agent.py`:

```python
def test_format_countdown_minutes_and_seconds():
    from polymarket_agent import format_countdown
    assert format_countdown(252) == "4m 12s"


def test_format_countdown_seconds_only():
    from polymarket_agent import format_countdown
    assert format_countdown(45) == "45s"


def test_format_countdown_zero():
    from polymarket_agent import format_countdown
    assert format_countdown(0) == "0s"


def test_format_countdown_negative():
    from polymarket_agent import format_countdown
    assert format_countdown(-5) == "0s"


def test_format_countdown_exact_minute():
    from polymarket_agent import format_countdown
    assert format_countdown(60) == "1m 0s"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_polymarket_agent.py::test_format_countdown_minutes_and_seconds -v
```

Expected: `ImportError: cannot import name 'format_countdown'`

- [ ] **Step 3: Add function to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
def format_countdown(seconds: int) -> str:
    """Format seconds as 'Xm Ys' or 'Xs'. Returns '0s' for zero or negative."""
    if seconds <= 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_polymarket_agent.py -v
```

Expected: 19 PASSED

- [ ] **Step 5: Commit**

```bash
git add polymarket_agent.py tests/test_polymarket_agent.py
git commit -m "feat: add format_countdown helper"
```

---

## Task 5: Auth, Client Setup & Market Pagination

**Files:**
- Modify: `polymarket_agent.py`

These functions make network calls. No unit tests — manual verification against live API.

- [ ] **Step 1: Add imports and constants to the top of `polymarket_agent.py`**

Add at the very top (before the existing `from datetime` line):

```python
import os
import time

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import MarketOrderArgs, OrderType, TradeParams
from py_clob_client.order_builder.constants import BUY

HOST = "https://clob.polymarket.com"
```

- [ ] **Step 2: Add `build_client` to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 3: Add `fetch_all_markets` to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 4: Manual smoke test — auth and market fetch**

Run:
```bash
python -c "
from polymarket_agent import build_client, fetch_all_markets, find_btc_5min_market
c = build_client()
print('Auth OK')
markets = fetch_all_markets(c)
print(f'Fetched {len(markets)} markets')
m = find_btc_5min_market(markets)
if m:
    print(f'Found: {m[\"question\"]}')
    print(f'Ends:  {m[\"end_date_iso\"]}')
else:
    print('No active BTC 5-min market found right now')
"
```

Expected: prints "Auth OK", market count, and either a market question or "No active..." message.

- [ ] **Step 5: Commit**

```bash
git add polymarket_agent.py
git commit -m "feat: add build_client and fetch_all_markets"
```

---

## Task 6: Countdown Display

**Files:**
- Modify: `polymarket_agent.py`

- [ ] **Step 1: Add `run_countdown` to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 2: Manual smoke test**

Run:
```bash
python -c "
from datetime import datetime, timezone, timedelta
from polymarket_agent import run_countdown
end = datetime.now(timezone.utc) + timedelta(seconds=5)
run_countdown(end)
print('done')
"
```

Expected: a live countdown from `5s remaining` down to `closed`, then prints "done".

- [ ] **Step 3: Commit**

```bash
git add polymarket_agent.py
git commit -m "feat: add run_countdown display"
```

---

## Task 7: Order Placement

**Files:**
- Modify: `polymarket_agent.py`

- [ ] **Step 1: Add `place_order` to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add polymarket_agent.py
git commit -m "feat: add place_order"
```

---

## Task 8: Resolution Polling

**Files:**
- Modify: `polymarket_agent.py`

- [ ] **Step 1: Add `poll_resolution` to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add polymarket_agent.py
git commit -m "feat: add poll_resolution"
```

---

## Task 9: Main Menu Loop

**Files:**
- Modify: `polymarket_agent.py`

- [ ] **Step 1: Add `main()` and entry point to `polymarket_agent.py`**

Append to `polymarket_agent.py`:

```python
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
```

- [ ] **Step 2: Run full unit test suite**

```bash
pytest tests/test_polymarket_agent.py -v
```

Expected: 19 PASSED (all prior pure-helper tests still green)

- [ ] **Step 3: End-to-end manual test**

```bash
python polymarket_agent.py
```

Walk through:
1. Agent prints "Looking up active BTC 5-min market..."
2. Menu appears with market question and countdown
3. Enter `3` → prints "Goodbye." and exits cleanly
4. Repeat run, enter `1` or `2` → order is placed, fill details printed, countdown runs, resolution displayed

- [ ] **Step 4: Commit**

```bash
git add polymarket_agent.py
git commit -m "feat: add main menu loop — polymarket_agent complete"
```

---

## Task 10: Push

- [ ] **Step 1: Final test run**

```bash
pytest tests/test_polymarket_agent.py -v
```

Expected: 19 PASSED

- [ ] **Step 2: Push**

```bash
git push
```
