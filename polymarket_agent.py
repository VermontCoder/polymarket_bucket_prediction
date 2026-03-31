import sys
import time

from datetime import datetime, timezone

from polymarket_interact import (
    build_client,
    find_active_btc_5min_market,
    get_token_ids,
    place_order,
    poll_resolution,
)


def format_countdown(seconds: int) -> str:
    """Format seconds as 'Xm Ys' or 'Xs'. Returns '0s' for zero or negative."""
    if seconds <= 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


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


def main():
    try:
        client = build_client()
    except EnvironmentError as e:
        print(f"Error: {e}")
        return

    print("\nLooking up active BTC 5-min market...")
    try:
        result = find_active_btc_5min_market(client)
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return
    if result is None:
        print("No active BTC 5-minute market found. Exiting.")
        return

    market, slug = result
    print(f"Found active market (slug: {slug})")
    up_token_id, down_token_id = get_token_ids(market)

    while True:
        remaining = seconds_until_next_five_min_interval()
        print(f"\nActive market: {market['question']}")
        print(f"Closes in: {remaining:.0f} seconds")
        print()
        print("1. Buy UP  (Yes)")
        print("2. Buy DOWN (No)")
        print("3. Exit")
        print()

        choice = input("Choice: ").strip()

        if choice == "3":
            print("Goodbye.")
            sys.exit(1)
        elif choice == "1":
            selected_token_id, side_label = up_token_id, "UP"
        elif choice == "2":
            selected_token_id, side_label = down_token_id, "DOWN"
        else:
            print("Invalid choice — enter 1, 2, or 3.")
            sys.exit(1)

        try:
            fill = place_order(client, selected_token_id, side_label)
        except Exception as e:
            print(f"Order error: {e}")
            sys.exit(1)

        if fill is None:
            print("No fill obtained. Returning.")
            continue
        else:
            break
        

    print("\nOrder filled. Waiting for market to close...")

    remaining = seconds_until_next_five_min_interval()
    time.sleep(int(remaining))

    print("\nMarket closed. Checking resolution...")

    try:
        poll_resolution(slug, fill)
    except Exception as e:
        print(f"Resolution error: {e}")


if __name__ == "__main__":
    main()
