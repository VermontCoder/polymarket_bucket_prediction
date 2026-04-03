MARKET_CONFIG = {
    "BTC_5": {
        "slug_prefix":         "btc-updown-5m",
        "binance_symbol":      "BTCUSDT",
        "file_prefix":         "btc_5",
        "bucket_rates_path":   "data/btc_bucket_rates.json",
        "smoothed_rates_path": "data/btc_smoothed_rates.json",
    },
    "ETH_5": {
        "slug_prefix":         "eth-updown-5m",
        "binance_symbol":      "ETHUSDT",
        "file_prefix":         "eth_5",
        "bucket_rates_path":   "data/eth_bucket_rates.json",
        "smoothed_rates_path": "data/eth_smoothed_rates.json",
    },
}


def parse_market_arg(value: str) -> str:
    """Normalize and validate a market CLI argument. Returns uppercase key."""
    key = value.upper()
    if key not in MARKET_CONFIG:
        valid = ", ".join(MARKET_CONFIG)
        raise ValueError(f"Unknown market '{value}'. Choose from: {valid}")
    return key
