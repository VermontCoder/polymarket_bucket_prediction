# Rich UI Design — polymarket_agent.py

**Date:** 2026-04-01

## Overview

Replace the existing `print()`/`input()` terminal UI in `polymarket_agent.py` with a Rich-based two-panel live display. The left panel shows the active market and order menu; the right panel shows a scrolling action log. The display refreshes every 2 seconds. Order placement is triggered immediately on keypress with no render-cycle delay.

---

## Threading Model

Three concurrent threads:

| Thread | Role |
|---|---|
| **Main (render)** | Runs `Rich Live`, refreshes layout every 2s from `AppState` |
| **Input** | Loops on `msvcrt.getwch()`, immediately acts on valid keypresses |
| **Resolution** | Existing — writes to `resolution_{slug}.log`, unchanged |

A fourth short-lived thread is spawned per order attempt to call `place_order()`.

All shared state lives in a single `AppState` dataclass. A `threading.Lock` guards every read/write to `AppState`.

---

## AppState

```python
@dataclass
class AppState:
    status: Status               # enum — see State Machine below
    market: dict | None          # current CLOB market dict
    slug: str | None             # current market slug
    up_token_id: str | None
    down_token_id: str | None
    fill: dict | None            # fill result from place_order(), or None
    log_lines: list[str]         # right panel log, capped at MAX_LOG_LINES
    lock: threading.Lock
```

`MAX_LOG_LINES` = 200 (only the last N that fit the panel height are rendered).

---

## State Machine

```
WAITING_FOR_ORDER
  → key 1/2: set status = ORDER_PLACED (under lock), then spawn order thread
  → key 3:   exit

ORDER_PLACED
  → key 3:            exit (only accepted input)
  → order filled:     store fill in AppState → WAITING_NEXT_MARKET
  → order not filled: log "No fill obtained." → WAITING_FOR_ORDER

WAITING_NEXT_MARKET
  → window elapses:
      → if fill exists: spawn resolution thread (writes to log file)
      → fetch next market (retry until found)
      → market found: clear fill, → WAITING_FOR_ORDER
```

**Critical ordering rule:** The status must be set to `ORDER_PLACED` under the lock *before* the order thread is spawned. This ensures that any keypress received between the status write and the thread start is already rejected by the input thread's guard check. No keypress after the initial 1/2 can trigger a second `place_order()` call until the current order resolves.

---

## UI Layout

```
┌─────────────────────────────┬──────────────────────────────┐
│  ACTIVE MARKET               │  LOG                         │
│                              │                              │
│  BTC 5-min Up/Down           │  > Looking up market...      │
│  btc-updown-5m-1234567890    │  > Found market (slug: ...)  │
│                              │  > Order placed: BUY UP      │
│  Closes in: 3m 42s           │  > Order ID: 0xabc...        │
│                              │  > Shares: 5.000             │
│  [1] Buy UP                  │  > Avg price: $0.650         │
│  [2] Buy DOWN                │  > Cost: $3.25               │
│  [3] Exit                    │  > No fill obtained.         │
│                              │  > Waiting for next market.. │
│  Press a key...              │                              │
└─────────────────────────────┴──────────────────────────────┘
```

**Left panel — WAITING_FOR_ORDER:**
- Market question and slug
- Live countdown ("Closes in: Xm Ys"), updated each render cycle
- Menu: `[1] Buy UP`, `[2] Buy DOWN`, `[3] Exit`
- Footer: "Press a key..."

**Left panel — ORDER_PLACED:**
- Market question and slug
- Live countdown
- Status line: "Bought UP at $0.65 — waiting for market close"
- `[3] Exit` only

**Left panel — WAITING_NEXT_MARKET:**
- "Waiting for next market window..."
- Countdown to next 5-min boundary

**Right panel:**
- Scrolling log of all main-thread status messages
- Newest entries at bottom
- Capped to panel height (last N lines rendered)
- All existing `print()` calls in `polymarket_agent.py` replaced with `state.log(msg)`

---

## Key Input

- `msvcrt.getwch()` used for single-keypress capture (Windows stdlib, no extra dependency)
- Input thread runs in a loop; ignores keypresses when `status == ORDER_PLACED` except `'3'`
- On valid keypress: immediately spawns a one-shot thread to call `place_order()` — input loop stays unblocked, no wait for render cycle

---

## File Changes

| File | Change |
|---|---|
| `polymarket_agent.py` | Full rewrite of `main()` and supporting functions; add `AppState`, `Status` enum, render function, input thread function |
| `polymarket_interact.py` | No changes — `place_order`, `poll_resolution`, etc. untouched |

---

## Out of Scope

- Resolution output displayed in the right panel (resolution thread continues writing to `resolution_{slug}.log`)
- Any changes to `polymarket_interact.py`
