import json
import os
import random
from session import Session
from visualizer import plot_bucket_predict_rates


def load_sessions(filepath: str) -> list[Session]:
    with open(filepath) as f:
        data = json.load(f)
    return [Session(s) for s in data]


def build_bucket_predict_rates(sessions: list[Session]) -> dict:
    totals = {}
    trues = {}
    for session in sessions:
        for key, rows in session.to_buckets().items():
            if key is None:
                continue
            for row in rows:
                if row.predict is None:
                    continue
                totals[key] = totals.get(key, 0) + 1
                trues[key] = trues.get(key, 0) + (1 if row.predict else 0)
    return {key: trues[key] / totals[key] for key in totals}


def save_bucket_rates(bucket_rates: dict, filepath: str) -> None:
    serializable = {f"{x},{y}": rate for (x, y), rate in bucket_rates.items()}
    with open(filepath, "w") as f:
        json.dump(serializable, f)


def load_bucket_rates(filepath: str) -> dict:
    with open(filepath) as f:
        raw = json.load(f)
    return {tuple(int(v) for v in key.split(",")): rate for key, rate in raw.items()}


def smooth_bucket_rates(bucket_rates: dict) -> dict:
    smoothed = {}
    for (x, y) in bucket_rates:
        neighbors = [
            (x + dx, y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if (dx, dy) != (0, 0)
        ]
        values = [bucket_rates[(x, y)]] + [bucket_rates[n] for n in neighbors if n in bucket_rates]
        smoothed[(x, y)] = sum(values) / len(values)
    return smoothed


BUCKET_RATES_CACHE = "data/bucket_rates.json"
SMOOTHED_RATES_CACHE = "data/smoothed_rates.json"

if __name__ == "__main__":
    if os.path.exists(BUCKET_RATES_CACHE) and os.path.exists(SMOOTHED_RATES_CACHE):
        print("Loading bucket rates from cache...")
        bucket_rates = load_bucket_rates(BUCKET_RATES_CACHE)
        smoothed_rates = load_bucket_rates(SMOOTHED_RATES_CACHE)
        print(f"Distinct buckets:  {len(bucket_rates)}")
    else:
        sessions = load_sessions("data/btc_polymarket_combined_20260325_134508_train.json")
        total_rows = sum(len(s.rows) for s in sessions)
        print(f"Sessions ingested: {len(sessions)}")
        print(f"Rows ingested:     {total_rows}")
        print()

        bucket_rates = build_bucket_predict_rates(sessions)
        smoothed_rates = smooth_bucket_rates(bucket_rates)
        print(f"Distinct buckets:  {len(bucket_rates)}")

        save_bucket_rates(bucket_rates, BUCKET_RATES_CACHE)
        save_bucket_rates(smoothed_rates, SMOOTHED_RATES_CACHE)
        print("Bucket rates saved to cache.")
    print()

    sample = random.sample(list(bucket_rates.items()), 25)
    sample.sort(key=lambda x: x[0])
    print(f"{'Bucket ID':<20} {'Predict True %'}")
    print("-" * 36)
    for key, rate in sample:
        print(f"{str(key):<20} {rate * 100:.1f}%")

    plot_bucket_predict_rates(bucket_rates, title="Raw — Predict True % per Bucket")
    plot_bucket_predict_rates(smoothed_rates, title="Smoothed — Predict True % per Bucket")
