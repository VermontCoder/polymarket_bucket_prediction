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


def split_unsplit_files() -> list[str]:
    """Find JSON files in data/ that lack a _train or _test suffix.

    For each one, split 80/20 (older sessions = train) and write
    sibling _train.json and _test.json files. Returns list of train
    file paths produced.
    """
    produced = []
    for fname in os.listdir("data"):
        if not fname.endswith(".json"):
            continue
        stem = fname[:-5]  # strip .json
        if stem.endswith("_train") or stem.endswith("_test"):
            continue

        src = os.path.join("data", fname)
        with open(src) as f:
            data = json.load(f)

        if not isinstance(data, list) or not data:
            continue

        split = int(len(data) * 0.8)
        train_data = data[:split]
        test_data = data[split:]

        train_path = os.path.join("data", f"{stem}_train.json")
        test_path = os.path.join("data", f"{stem}_test.json")

        with open(train_path, "w") as f:
            json.dump(train_data, f)
        with open(test_path, "w") as f:
            json.dump(test_data, f)

        print(f"Split {fname}: {len(train_data)} train / {len(test_data)} test")
        print(f"  -> {train_path}")
        print(f"  -> {test_path}")
        produced.append(train_path)

    return produced


def find_train_files() -> list[str]:
    """Return all _train.json files in data/."""
    return [
        os.path.join("data", f)
        for f in sorted(os.listdir("data"))
        if f.endswith("_train.json")
    ]


if __name__ == "__main__":
    # Split any unsplit JSON files first
    split_unsplit_files()

    train_files = find_train_files()
    if not train_files:
        print("No _train.json files found in data/. Exiting.")
        raise SystemExit(1)

    # Load all train sessions across all train files
    all_sessions = []
    for path in train_files:
        sessions = load_sessions(path)
        all_sessions.extend(sessions)
        print(f"Loaded {len(sessions)} sessions from {path}")

    total_rows = sum(len(s.rows) for s in all_sessions)
    print(f"\nTotal sessions: {len(all_sessions)}")
    print(f"Total rows:     {total_rows}")
    print()

    bucket_rates = build_bucket_predict_rates(all_sessions)
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
