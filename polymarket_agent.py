import json
import time
import threading
from datetime import datetime, timezone

from dataclasses import dataclass, field
from enum import Enum, auto

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from polymarket_interact import (
    build_client,
    find_active_btc_5min_market,
    get_token_ids,
    place_order,
    poll_resolution,
)
from market_data import fetch_open_price_for_window, fetch_btc5m_snapshot
from signal_eval import evaluate_signal, load_smoothed_rates

MAX_LOG_LINES = 200


class Status(Enum):
    WAITING_FOR_ORDER = auto()
    ORDER_PLACED = auto()
    WAITING_NEXT_MARKET = auto()


@dataclass
class AppState:
    status: Status
    market: dict | None
    slug: str | None
    up_token_id: str | None
    down_token_id: str | None
    fill: dict | None
    log_lines: list[str]
    lock: threading.Lock
    run_log_path: str = ""
    cumulative_pnl: float = 0.0
    smoothed_rates: dict = field(default_factory=dict)
    price_to_beat: float | None = None
    last_snapshot: dict | None = None
    threshold: float = 13.0
    manual: bool = False

    def log(self, msg: str) -> None:
        with self.lock:
            self.log_lines.append(msg)
            if len(self.log_lines) > MAX_LOG_LINES:
                self.log_lines = self.log_lines[-MAX_LOG_LINES:]


def build_left_panel(state: AppState, seconds_remaining: float) -> Panel:
    """Build the left Rich Panel from current AppState."""
    countdown = format_countdown(int(seconds_remaining))
    t = Text()

    if state.status == Status.WAITING_NEXT_MARKET:
        t.append("Waiting for next market window...\n\n", style="bold yellow")
        t.append(f"Next window in: {countdown}", style="cyan")
    else:
        question = state.market.get("question", "") if state.market else ""
        t.append(f"{question}\n", style="bold white")
        t.append(f"{state.slug or ''}\n\n", style="dim")
        t.append(f"Closes in: {countdown}\n\n", style="cyan")

        # Always show live price data when available
        if state.price_to_beat is not None:
            t.append(f"Price to beat: {state.price_to_beat:.2f}\n", style="dim")
        if state.last_snapshot is not None:
            snap = state.last_snapshot
            cp = snap.get("current_price")
            ua = snap.get("up_ask")
            da = snap.get("down_ask")
            diff = snap.get("diff_pct")
            if cp is not None:
                t.append(f"Current price: {cp:.2f}\n", style="white")
            if diff is not None:
                diff_style = "green" if diff >= 0 else "red"
                t.append(f"Diff: {diff:+.4f}%\n", style=diff_style)
            if ua is not None and da is not None:
                t.append(f"Up ask: {ua:.0f}c  Down ask: {da:.0f}c\n", style="dim")
        t.append("\n")

        if state.status == Status.WAITING_FOR_ORDER:
            pnl = state.cumulative_pnl
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            pnl_style = "green" if pnl >= 0 else "red"
            t.append(f"Run P&L: {pnl_str}\n\n", style=pnl_style)

            if state.manual:
                t.append("[1] Buy UP\n", style="green")
                t.append("[2] Buy DOWN\n", style="red")
                t.append("[X] Exit\n\n", style="dim")
                t.append("Press a key...", style="italic dim")
            else:
                t.append("Auto mode — signal will fire automatically\n\n", style="italic dim")
                t.append("[X] Exit", style="dim")

        elif state.status == Status.ORDER_PLACED:
            if state.fill:
                side = state.fill.get("side_label", "?")
                cost = state.fill.get("cost", 0.0)
                t.append(f"Bought {side} at ${cost:.2f} — waiting for market close\n\n",
                         style="bold green")
            t.append("[X] Exit\n", style="dim")

    return Panel(t, title="ACTIVE MARKET", border_style="blue")


def build_right_panel(state: AppState, panel_height: int) -> Panel:
    """Build the right Rich Panel showing the action log."""
    with state.lock:
        lines = list(state.log_lines)
    visible_count = max(0, panel_height - 2)
    visible = lines[-visible_count:] if visible_count > 0 else []
    t = Text("\n".join(f"> {line}" for line in visible))
    return Panel(t, title="LOG", border_style="cyan")


def run_order_thread(
    state: AppState,
    client,
    token_id: str,
    side_label: str,
    price: float = 0.99,
) -> None:
    """Called on a one-shot thread. Places the order and updates AppState."""
    state.log(f"Placing order: BUY {side_label} at {price:.2f}...")
    try:
        fill = place_order(client, token_id, side_label, price)
    except Exception as e:
        state.log(f"Order error: {e}")
        with state.lock:
            state.status = Status.WAITING_FOR_ORDER
        return

    if fill is None:
        state.log("No fill obtained.")
        with state.lock:
            state.status = Status.WAITING_FOR_ORDER
        return

    state.log(f"Order filled: BUY {side_label}")
    state.log(f"  Order ID:  {fill['order_id']}")
    state.log(f"  Shares:    {fill['shares']:.3f}")
    state.log(f"  Cost:      ${fill['cost']:.2f}")
    with state.lock:
        state.fill = fill
        state.status = Status.WAITING_NEXT_MARKET


def run_input_thread(state: AppState, client, stop_event: threading.Event) -> None:
    """Runs on a dedicated thread. Reads single keypresses and acts immediately.

    In auto mode: only X exits.
    In manual mode: 1=Buy UP, 2=Buy DOWN, X=Exit.
    """
    import msvcrt
    while not stop_event.is_set():
        if not msvcrt.kbhit():
            time.sleep(0.05)
            continue
        key = msvcrt.getwch().lower()

        with state.lock:
            current_status = state.status
            up_token_id = state.up_token_id
            down_token_id = state.down_token_id
            manual = state.manual

        if key == 'x':
            state.log("Exiting...")
            stop_event.set()
            return

        if not manual:
            continue  # auto mode: only X accepted

        if current_status != Status.WAITING_FOR_ORDER:
            continue  # only X accepted in other states

        if key == '1':
            token_id, side_label = up_token_id, "UP"
        elif key == '2':
            token_id, side_label = down_token_id, "DOWN"
        else:
            continue

        # Set ORDER_PLACED under lock BEFORE spawning thread (critical ordering rule)
        with state.lock:
            state.status = Status.ORDER_PLACED

        threading.Thread(
            target=run_order_thread,
            args=(state, client, token_id, side_label),
            daemon=True,
        ).start()


def _read_cumulative_pnl(log_path: str) -> float:
    """Sum the 'pnl' field from all resolved JSON lines in the run log."""
    total = 0.0
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    total += record.get("pnl", 0.0)
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return total


def advance_to_next_market(state: AppState, client) -> None:
    """Called from render loop when WAITING_NEXT_MARKET and window has elapsed.

    Spawns resolution thread if there was a fill, then fetches the next market.
    Transitions to WAITING_FOR_ORDER once a new active market is found.
    """
    with state.lock:
        fill = state.fill
        slug = state.slug

    if fill is not None:
        state.log(f"Spawning resolution thread for {slug}...")
        threading.Thread(
            target=_resolve_in_background,
            args=(slug, fill, state.run_log_path),
            daemon=True,
        ).start()

    state.log("Looking up next market...")
    while True:
        try:
            result = find_active_btc_5min_market(client)
        except Exception as e:
            state.log(f"Error fetching market: {e} — retrying...")
            time.sleep(5)
            continue

        if result is None:
            state.log("No active market yet — retrying...")
            time.sleep(5)
            continue

        market, new_slug = result
        try:
            up_token_id, down_token_id = get_token_ids(market)
        except ValueError as e:
            state.log(f"Bad market tokens: {e} — retrying...")
            time.sleep(5)
            continue

        state.log(f"Found new market: {new_slug}")
        with state.lock:
            state.market = market
            state.slug = new_slug
            state.up_token_id = up_token_id
            state.down_token_id = down_token_id
            state.fill = None
            state.cumulative_pnl = _read_cumulative_pnl(state.run_log_path)
            state.status = Status.WAITING_FOR_ORDER
        return


def format_countdown(seconds: int) -> str:
    """Format seconds as 'Xm Ys' or 'Xs'. Returns '0s' for zero or negative."""
    if seconds <= 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"



def seconds_until_next_five_min_interval():
    """
    Calculates the number of seconds from a given timestamp to the next
    five-minute interval boundary (e.g., hh:00:00, hh:05:00, ..., hh:55:00).

    Returns:
        The number of seconds (float) until the next five-minute interval.
    """
    timestamp = time.time()
    interval_seconds = 300  # 5 minutes * 60 seconds/minute
    next_interval_timestamp = timestamp + interval_seconds - (timestamp % interval_seconds)
    seconds_remaining = next_interval_timestamp - timestamp
    return seconds_remaining // 1


def run_headless_mode(state: AppState, stop_event: threading.Event) -> None:
    """Headless main loop. Drains state.log_lines to stdout. Exits on stop_event or 'x' key."""
    import msvcrt
    while not stop_event.is_set():
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            if key.lower() == 'x':
                state.log("Exiting (headless)...")
                stop_event.set()
                return

        with state.lock:
            new_lines = state.log_lines[:]
            state.log_lines = []

        for line in new_lines:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {line}", flush=True)

        stop_event.wait(timeout=0.1)


def run_data_thread(state: AppState, stop_event: threading.Event, client) -> None:
    """Polls market data every 2 seconds, evaluates signal, auto-places order if signal fires."""
    while not stop_event.is_set():
        with state.lock:
            up_id = state.up_token_id
            down_id = state.down_token_id
            slug = state.slug
            price_to_beat = state.price_to_beat
            smoothed_rates = state.smoothed_rates
            current_status = state.status

        if up_id and down_id and slug:
            window_end = _window_start() + 300
            try:
                snap = fetch_btc5m_snapshot(up_id, down_id, window_end_epoch=window_end)
                if snap and price_to_beat is not None:
                    cp = snap.get("current_price")
                    if cp is not None:
                        snap["diff_pct"] = (cp - price_to_beat) / price_to_beat * 100
                with state.lock:
                    state.last_snapshot = snap
            except Exception as e:
                state.log(f"Data fetch error: {e}")
                stop_event.wait(timeout=2)
                continue

            if current_status == Status.WAITING_FOR_ORDER and price_to_beat is not None and snap and not state.manual:
                signal = evaluate_signal(snap, price_to_beat, smoothed_rates, threshold=state.threshold)
                if signal is not None:
                    direction, ask_cents = signal
                    token_id = up_id if direction == "UP" else down_id
                    price = ask_cents / 100
                    state.log(f"Signal: BUY {direction} at {price:.2f} (ask={ask_cents:.0f}c)")
                    with state.lock:
                        state.status = Status.ORDER_PLACED
                    threading.Thread(
                        target=run_order_thread,
                        args=(state, client, token_id, direction, price),
                        daemon=True,
                    ).start()

        stop_event.wait(timeout=2)


def _window_start() -> int:
    return (int(time.time()) // 300) * 300


def _capture_price_to_beat(state: AppState, window_start: int) -> None:
    """Fetch the Binance open price for the given window and store in state.price_to_beat."""
    try:
        price = fetch_open_price_for_window(window_start)
    except Exception as e:
        state.log(f"Could not fetch open price: {e}")
        return
    if price is None:
        state.log("Open price unavailable — price_to_beat not set")
        return
    with state.lock:
        state.price_to_beat = price
    state.log(f"Price to beat: {price:.2f}")


def _resolve_in_background(slug: str, fill: dict, log_path: str) -> None:
    with open(log_path, "a") as f:
        try:
            poll_resolution(slug, fill, out=f)
        except Exception as e:
            import json
            f.write(json.dumps({"slug": slug, "error": str(e)}) + "\n")
            f.flush()


def run_ui_mode(state: AppState, client, stop_event: threading.Event) -> None:
    """Rich Live two-panel display loop."""
    console = Console()
    layout = Layout()
    layout.split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    _advance_pending = False
    _price_capture_pending = False

    with Live(layout, console=console, refresh_per_second=0.5, screen=True):
        while not stop_event.is_set():
            seconds_remaining = seconds_until_next_five_min_interval()
            panel_height = console.height

            with state.lock:
                current_status = state.status

            layout["left"].update(build_left_panel(state, seconds_remaining))
            layout["right"].update(build_right_panel(state, panel_height))

            # Capture price-to-beat exactly at boundary
            if seconds_remaining <= 1 and not _price_capture_pending:
                _price_capture_pending = True
                ws = _window_start() + 300  # next window start
                threading.Thread(
                    target=_capture_price_to_beat,
                    args=(state, ws),
                    daemon=True,
                ).start()

            # Trigger market advance when window elapses and not already running
            if current_status in (Status.WAITING_NEXT_MARKET, Status.WAITING_FOR_ORDER) and seconds_remaining <= 3 and not _advance_pending:
                _advance_pending = True
                def _advance():
                    time.sleep(4)
                    advance_to_next_market(state, client)
                threading.Thread(target=_advance, daemon=True).start()

            # Reset flags once we're in a fresh window
            if current_status == Status.WAITING_FOR_ORDER and seconds_remaining > 10:
                _advance_pending = False
                _price_capture_pending = False

            time.sleep(2)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true",
                        help="Manual mode: press 1/2 to buy UP/DOWN instead of auto-signal")
    parser.add_argument("--threshold", type=float, default=13.0,
                        help="Signal threshold: percent above ask required to place order (default: 13)")
    args = parser.parse_args()

    console = Console()

    try:
        client = build_client()
    except EnvironmentError as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    try:
        smoothed_rates = load_smoothed_rates("data/smoothed_rates.json")
    except Exception as e:
        console.print(f"[red]Could not load smoothed rates:[/red] {e}")
        return

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_log_path = f"logs/resolution_{run_ts}.log"

    state = AppState(
        status=Status.WAITING_FOR_ORDER,
        market=None,
        slug=None,
        up_token_id=None,
        down_token_id=None,
        fill=None,
        log_lines=[],
        lock=threading.Lock(),
        run_log_path=run_log_path,
        smoothed_rates=smoothed_rates,
        threshold=args.threshold,
        manual=args.manual,
    )

    # Initial market fetch
    state.log("Looking up active BTC 5-min market...")
    try:
        result = find_active_btc_5min_market(client)
    except Exception as e:
        console.print(f"[red]Error fetching market:[/red] {e}")
        return

    if result is None:
        console.print("No active BTC 5-minute market found. Exiting.")
        return

    market, slug = result
    try:
        up_token_id, down_token_id = get_token_ids(market)
    except ValueError as e:
        console.print(f"[red]Bad market tokens:[/red] {e}")
        return

    with state.lock:
        state.market = market
        state.slug = slug
        state.up_token_id = up_token_id
        state.down_token_id = down_token_id
    state.log(f"Found market: {slug}")
    if args.manual:
        state.log("Mode: MANUAL (press 1/2 to buy)")
    else:
        state.log(f"Mode: AUTO  threshold={args.threshold:.0f}%")

    # Fetch price-to-beat for the current window in background
    threading.Thread(
        target=_capture_price_to_beat,
        args=(state, _window_start()),
        daemon=True,
    ).start()

    stop_event = threading.Event()

    # Start data polling thread
    threading.Thread(
        target=run_data_thread,
        args=(state, stop_event, client),
        daemon=True,
    ).start()

    threading.Thread(
        target=run_input_thread,
        args=(state, client, stop_event),
        daemon=True,
    ).start()
    try:
        run_ui_mode(state, client, stop_event)
    except KeyboardInterrupt:
        stop_event.set()


if __name__ == "__main__":
    main()
