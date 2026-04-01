import time
import threading

from dataclasses import dataclass
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

        if state.status == Status.WAITING_FOR_ORDER:
            t.append("[1] Buy UP\n", style="green")
            t.append("[2] Buy DOWN\n", style="red")
            t.append("[3] Exit\n\n", style="dim")
            t.append("Press a key...", style="italic dim")

        elif state.status == Status.ORDER_PLACED:
            if state.fill:
                side = state.fill.get("side_label", "?")
                cost = state.fill.get("cost", 0.0)
                t.append(f"Bought {side} at ${cost:.2f} — waiting for market close\n\n",
                         style="bold green")
            t.append("[3] Exit\n", style="dim")

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
) -> None:
    """Called on a one-shot thread. Places the order and updates AppState."""
    state.log(f"Placing order: BUY {side_label}...")
    try:
        fill = place_order(client, token_id, side_label)
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
    """Runs on a dedicated thread. Reads single keypresses and acts immediately."""
    import msvcrt
    while not stop_event.is_set():
        if not msvcrt.kbhit():
            time.sleep(0.05)
            continue
        key = msvcrt.getwch()

        with state.lock:
            current_status = state.status
            up_token_id = state.up_token_id
            down_token_id = state.down_token_id

        if key == '3':
            state.log("Exiting...")
            stop_event.set()
            return

        if current_status != Status.WAITING_FOR_ORDER:
            continue  # only '3' accepted in other states

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
            args=(slug, fill),
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


def _resolve_in_background(slug: str, fill: dict) -> None:
    log_path = f"resolution_{slug}.log"
    with open(log_path, "w") as f:
        try:
            poll_resolution(slug, fill, out=f)
        except Exception as e:
            f.write(f"\nResolution error: {e}\n")


def main() -> None:
    console = Console()

    try:
        client = build_client()
    except EnvironmentError as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    state = AppState(
        status=Status.WAITING_FOR_ORDER,
        market=None,
        slug=None,
        up_token_id=None,
        down_token_id=None,
        fill=None,
        log_lines=[],
        lock=threading.Lock(),
    )

    # Initial market fetch before starting the Live display
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

    stop_event = threading.Event()

    input_thread = threading.Thread(
        target=run_input_thread,
        args=(state, client, stop_event),
        daemon=True,
    )
    input_thread.start()

    layout = Layout()
    layout.split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    _advance_pending = False  # True while advance_to_next_market is running

    with Live(layout, console=console, refresh_per_second=0.5, screen=True):
        while not stop_event.is_set():
            seconds_remaining = seconds_until_next_five_min_interval()
            panel_height = console.height

            with state.lock:
                current_status = state.status

            layout["left"].update(build_left_panel(state, seconds_remaining))
            layout["right"].update(build_right_panel(state, panel_height))

            # Trigger market advance when window elapses and not already running
            if current_status in (Status.WAITING_NEXT_MARKET, Status.WAITING_FOR_ORDER) and seconds_remaining <= 3 and not _advance_pending:
                _advance_pending = True
                def _advance():
                    time.sleep(4)  # wait a few seconds to ensure new market is active
                    advance_to_next_market(state, client)
                threading.Thread(target=_advance, daemon=True).start()

            # Reset advance flag once we're back to WAITING_FOR_ORDER in a fresh window
            if current_status == Status.WAITING_FOR_ORDER and seconds_remaining > 10:
                _advance_pending = False

            time.sleep(2)


if __name__ == "__main__":
    main()
