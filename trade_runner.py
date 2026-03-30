from dataclasses import dataclass


@dataclass
class TradeResult:
    session_id:    str
    outcome:       str        # UP / DOWN
    direction:     str        # UP / DOWN — side with the higher ask
    correct:       bool       # direction == outcome
    row_timestamp: str
    bucket:        tuple
    ask_price:     float      # cents
    smoothed_rate: float      # 0.0–1.0
    shares_bought: float
    cost:          float      # dollars
    payout:        float      # dollars
    pnl:           float      # dollars
