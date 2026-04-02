import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signal_eval import evaluate_signal, load_smoothed_rates


def _snap(up_ask, down_ask, current_price, time_to_close):
    return {
        "up_ask": up_ask,
        "down_ask": down_ask,
        "current_price": current_price,
        "time_to_close": time_to_close,
    }


def test_signal_fires_primary_up():
    # up_ask=70 > down_ask=30 → UP dominant
    # diff_pct = (84100 - 84000) / 84000 * 100 = 0.119...
    # y = clamp(int(0.119 * 300 + 150)) = 185
    # x = 120000 // 2000 = 60
    # bucket (60,185), threshold=(70+13)/100=0.83, rate=0.84 → fires
    snap = _snap(up_ask=70.0, down_ask=30.0, current_price=84100.0, time_to_close=120000)
    result = evaluate_signal(snap, price_to_beat=84000.0, smoothed_rates={(60, 185): 0.84}, threshold=13)
    assert result is not None
    direction, ask_cents = result
    assert direction == "UP"
    assert ask_cents == 70.0


def test_signal_fires_contrarian_down():
    # down_ask=65 > up_ask=35 → DOWN dominant, contrarian (buy UP minority) fires
    # diff_pct = 0.0, y=150, x=50
    # contrarian_rate = 1 - 0.30 = 0.70
    # contrarian threshold = (35+13)/100 = 0.48 → 0.70 >= 0.48 fires
    snap = _snap(up_ask=35.0, down_ask=65.0, current_price=84000.0, time_to_close=100000)
    result = evaluate_signal(snap, price_to_beat=84000.0, smoothed_rates={(50, 150): 0.30}, threshold=13)
    assert result is not None
    direction, ask_cents = result
    assert direction == "UP"   # contrarian of DOWN dominant = buy UP (minority)
    assert ask_cents == 35.0


def test_signal_below_threshold_returns_none():
    snap = _snap(up_ask=70.0, down_ask=30.0, current_price=84100.0, time_to_close=120000)
    # rate=0.82, threshold=(70+13)/100=0.83 → 0.82 < 0.83 → no fire
    result = evaluate_signal(snap, price_to_beat=84000.0, smoothed_rates={(60, 185): 0.82}, threshold=13)
    assert result is None


def test_signal_missing_ask_returns_none():
    snap = _snap(up_ask=None, down_ask=60.0, current_price=84000.0, time_to_close=120000)
    assert evaluate_signal(snap, price_to_beat=84000.0, smoothed_rates={}, threshold=13) is None


def test_signal_no_price_to_beat_returns_none():
    snap = _snap(up_ask=70.0, down_ask=30.0, current_price=84000.0, time_to_close=120000)
    assert evaluate_signal(snap, price_to_beat=None, smoothed_rates={(60, 150): 0.90}, threshold=13) is None


def test_signal_bucket_not_in_rates_returns_none():
    snap = _snap(up_ask=70.0, down_ask=30.0, current_price=84100.0, time_to_close=120000)
    assert evaluate_signal(snap, price_to_beat=84000.0, smoothed_rates={}, threshold=13) is None


def test_signal_ttc_out_of_range_returns_none():
    snap = _snap(up_ask=70.0, down_ask=30.0, current_price=84100.0, time_to_close=400000)
    assert evaluate_signal(snap, price_to_beat=84000.0, smoothed_rates={(200, 185): 0.90}, threshold=13) is None


def test_load_smoothed_rates(tmp_path):
    import json
    path = tmp_path / "rates.json"
    path.write_text(json.dumps({"60,185": 0.84, "50,150": 0.72}))
    rates = load_smoothed_rates(str(path))
    assert rates[(60, 185)] == 0.84
    assert rates[(50, 150)] == 0.72
