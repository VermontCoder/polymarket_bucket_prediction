class Row:
    def __init__(self, data: dict):
        self.timestamp = str(data["timestamp"])
        self.up_bid = float(data["up_bid"]) if data["up_bid"] is not None else None
        self.up_ask = float(data["up_ask"]) if data["up_ask"] is not None else None
        self.down_bid = float(data["down_bid"]) if data["down_bid"] is not None else None
        self.down_ask = float(data["down_ask"]) if data["down_ask"] is not None else None
        self.current_price = float(data["current_price"])
        self.diff_pct = float(data["diff_pct"]) if data["diff_pct"] is not None else None
        self.diff_usd = float(data["diff_usd"]) if data["diff_usd"] is not None else None
        ttc = data.get("time_to_close")
        self.time_to_close = int(ttc) if ttc is not None else None
        self.predict = None

    def __repr__(self):
        return (
            f"Row(timestamp={self.timestamp}, price={self.current_price}, "
            f"diff_pct={self.diff_pct}, time_to_close={self.time_to_close})"
        )
