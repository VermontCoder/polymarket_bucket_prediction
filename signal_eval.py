import json
import random


def load_smoothed_rates(path: str) -> dict:
    """Load smoothed bucket rates from a JSON file. Keys are (x,y) int tuples."""
    with open(path) as f:
        raw = json.load(f)
    return {tuple(int(v) for v in key.split(",")): rate for key, rate in raw.items()}


def evaluate_signal(
    snapshot: dict,
    price_to_beat: float | None,
    smoothed_rates: dict,
    threshold: float = 13,
) -> tuple[str, float] | None:
    """Evaluate the bucket signal on a live snapshot dict.

    snapshot keys required: up_ask, down_ask (cents, 0-100), current_price, time_to_close (ms).
    price_to_beat: Binance open price at window start.

    Returns (direction, ask_price_cents) if signal fires, else None.
    direction is "UP" or "DOWN". ask_price_cents is the ask of the side to buy.
    """
    if price_to_beat is None:
        return None

    up_ask = snapshot.get("up_ask")
    down_ask = snapshot.get("down_ask")
    current_price = snapshot.get("current_price")
    time_to_close = snapshot.get("time_to_close")

    if up_ask is None or down_ask is None:
        return None
    if up_ask == down_ask:
        return None
    if current_price is None:
        return None
    if time_to_close is None or time_to_close < 0 or time_to_close > 300000:
        return None

    diff_pct = (current_price - price_to_beat) / price_to_beat * 100

    x = int(time_to_close) // 2000
    y = max(0, min(299, int(diff_pct * 300 + 150)))
    bucket = (x, y)

    if bucket not in smoothed_rates:
        return None

    if up_ask > down_ask:
        dominant_dir, dominant_ask = "UP", up_ask
        minority_dir, minority_ask = "DOWN", down_ask
    else:
        dominant_dir, dominant_ask = "DOWN", down_ask
        minority_dir, minority_ask = "UP", up_ask

    smoothed_rate = smoothed_rates[bucket]
    contrarian_rate = 1.0 - smoothed_rate

    primary_margin = smoothed_rate - (dominant_ask + threshold) / 100
    contrarian_margin = contrarian_rate - (minority_ask + threshold) / 100

    primary_fires = primary_margin >= 0
    contrarian_fires = contrarian_margin >= 0

    if not primary_fires and not contrarian_fires:
        return None
    if primary_fires and not contrarian_fires:
        return dominant_dir, dominant_ask
    if contrarian_fires and not primary_fires:
        return minority_dir, minority_ask

    # Both fire: take the larger margin; break ties randomly
    if primary_margin > contrarian_margin:
        return dominant_dir, dominant_ask
    elif contrarian_margin > primary_margin:
        return minority_dir, minority_ask
    else:
        if random.random() < 0.5:
            return dominant_dir, dominant_ask
        return minority_dir, minority_ask
