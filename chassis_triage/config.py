
from __future__ import annotations

# --- Human-review routing knobs ---
HIGH_COST_THRESHOLD_USD: float = 2_500.0   
CONF_MIN: float = 0.5                       

# --- Retire-vs-repair economics ---
RETIRE_COST_FRACTION: float = 0.6           
TYPICAL_SERVICE_LIFE_YEARS: int = 15        

# --- FMCSA out-of-service rule constants ---
TIRE_MIN_TREAD_32NDS: int = 2              
BRAKES_OOS_PCT: int = 20                 