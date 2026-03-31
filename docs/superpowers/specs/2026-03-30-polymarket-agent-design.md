# polymarket_agent.py — Design Spec
**Date:** 2026-03-30

## Overview

A standalone console script that places real market buy orders on Polymarket's 5-minute BTC UP/DOWN markets, displays fill details, counts down to session close, then reports profit or loss.

---

## Credentials & Environment

`.env` (never committed — added to `.gitignore`):

```
POLY_PRIVATE_KEY=0x<64-char hex>
POLY_CHAIN_ID=137
```

The API key, secret, and passphrase are **derived at runtime** from the private key via `client.create_or_derive_api_creds()`. They are not stored.

`python-dotenv` loads the `.env` file at startup.

---

## Architecture

`polymarket_agent.py` is self-contained. It does not import from `trade_runner.py` or `main.py`.

**Dependencies:**
```
py-clob-client
python-dotenv
```

**Startup sequence:**
1. Load `POLY_PRIVATE_KEY` and `POLY_CHAIN_ID` from `.env`
2. Instantiate `ClobClient(host, key=pk, chain_id=POLYGON)` (L1 auth)
3. Call `client.create_or_derive_api_creds()` → `ApiCreds(api_key, api_secret, api_passphrase)`
4. Call `client.set_api_creds(creds)` (upgrades to L2 auth)
5. Enter menu loop

---

## Market Lookup

Called once per menu cycle, before displaying choices.

1. Paginate `client.get_markets()` (follow `next_cursor` until `"LTE="`)
2. Filter for: `active == true`, `closed == false`, `question` contains `"BTC"` or `"Bitcoin"`, `question` contains `"5 min"` or `"5-min"` or `"5 minute"`
3. Among matches, pick the one whose `end_date_iso` is the nearest future UTC time
4. From its `tokens` array, identify:
   - **UP token:** `outcome == "Yes"` on a "Will BTC be higher" question
   - **DOWN token:** `outcome == "No"` on the same question
5. Store `condition_id`, `up_token_id`, `down_token_id`, `end_date_iso`

If no active market is found, print an error and exit.

---

## Menu Loop

```
Active market: Will BTC be higher at 3:45 PM UTC?
Closes in: 4m 12s

1. Buy UP  (Yes)
2. Buy DOWN (No)
3. Exit

Choice:
```

---

## Order Flow

User selects 1 or 2.

**Place order:**
```python
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

order_args = MarketOrderArgs(
    token_id=selected_token_id,
    amount=5.0,          # $5 USDC
    side=BUY,
    order_type=OrderType.FOK,
)
signed = client.create_market_order(order_args)
resp = client.post_order(signed, orderType=OrderType.FOK)
```

**Response handling:**
- If `resp["success"] == False`: print `resp["errorMsg"]`, return to menu
- `order_id = resp["orderID"]`

**Fill details (separate call):**
After a 2-second wait, call `client.get_order(order_id)`:
- `size_matched` — shares filled
- `original_size` — shares requested

Average fill price requires `client.get_trades(TradeParams(asset_id=token_id))`:
- Each trade record has `price` and `size`
- Compute: `sum(price * size for t in trades) / sum(size for t in trades)`

**Display after fill:**
```
Order placed: BUY UP
  Order ID:   0xabc123...
  Shares:     4.962
  Avg price:  $0.537
  Cost:       $2.69
```

---

## Countdown & Resolution

After a successful fill, display a live countdown to `end_date_iso`:

```
Waiting for market close...  [ 3m 44s remaining ]
```

Update every second using `\r` (carriage return) to overwrite the line in place.

When countdown reaches zero, poll `client.get_market(condition_id)` every 5 seconds until `closed == true`, up to 60 seconds.

**Determine outcome:**
```python
for token in market["tokens"]:
    if token["winner"]:
        winning_token_id = token["token_id"]
won = (winning_token_id == selected_token_id)
```

**Payout calculation:**
```
payout  = shares_filled * 1.00  if won  else 0.00
pnl     = payout - cost
```

**Display:**
```
Result: WIN  — bought UP, resolved UP
  Shares: 4.962  |  Paid: $2.69  |  Payout: $4.96  |  P&L: +$2.27

--- or ---

Result: LOSS — bought UP, resolved DOWN
  Shares: 4.962  |  Paid: $2.69  |  Payout: $0.00  |  P&L: -$2.69
```

If `closed` is still `false` after 60 seconds of polling:
```
Resolution pending — check Polymarket for order 0xabc123...
```

After resolution (or timeout), return to the menu loop.

---

## Error Handling

| Situation | Behaviour |
|---|---|
| `.env` missing or key absent | Print clear error, exit |
| No active BTC 5-min market found | Print error, exit |
| `post_order` returns `success: false` | Print `errorMsg`, return to menu |
| Order not filled (`size_matched == "0"`) | Print "Order not filled", return to menu |
| Resolution polling timeout (60s) | Print "Resolution pending", return to menu |
| Any unexpected exception | Print exception message, return to menu |

---

## File Layout

- **`polymarket_agent.py`** — new standalone script
- **`.env`** — new file, not committed
- **`.gitignore`** — add `.env` entry
- **`requirements.txt`** (or note in README) — add `py-clob-client` and `python-dotenv`

No changes to existing files except `.gitignore`.
