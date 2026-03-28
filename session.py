from row import Row


class Session:
    def __init__(self, data: dict):
        self.session_id = str(data["session_id"])
        self.outcome = str(data["outcome"])
        self.hour = int(data["hour"])
        self.day = int(data["day"])
        self.diff_pct_prev_session = float(data["diff_pct_prev_session"]) if data["diff_pct_prev_session"] is not None else None
        self.diff_pct_hour = float(data["diff_pct_hour"]) if data["diff_pct_hour"] is not None else None
        self.avg_pct_variance_hour = float(data["avg_pct_variance_hour"]) if data["avg_pct_variance_hour"] is not None else None
        self.rows = [Row(r) for r in data["rows"]]

    def to_buckets(self) -> dict:
        buckets = {}
        for row in self.rows:
            ttc = row.time_to_close
            if ttc is None or ttc < 0 or ttc > 300000:
                key = None
            elif row.diff_pct is None:
                key = None
            else:
                x = ttc // 2000
                y = int(row.diff_pct * 300 + 150)
                y = max(0, min(299, y))
                key = (x, y)
            buckets.setdefault(key, []).append(row)

        for row in self.rows:
            if row.diff_pct is None:
                row.predict = None
            else:
                row_direction = "UP" if row.diff_pct >= 0 else "DOWN"
                row.predict = row_direction == self.outcome

        return buckets

    def __repr__(self):
        return (
            f"Session(id={self.session_id}, outcome={self.outcome}, "
            f"rows={len(self.rows)})"
        )
