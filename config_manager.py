import json
import os
import shutil

CONFIG_DIR = "configs"
DEFAULT_PROFILE = "default.json"
ACTIVE_PROFILE_FILE = os.path.join(CONFIG_DIR, ".active_profile")

DEFAULT_CONFIG = {
    "General": {
        "mode": "Backtest",  # Backtest, Paper, Live
        "bot_status": "Stopped" # Stopped, Running, Paused
    },
    "Market": {
        "symbol": "es",
        "timeframe": "5m",
        "htf": "1h",
        "london_start": 60,   # 1:00 AM (in minutes from midnight)
        "london_end": 360,    # 6:00 AM
        "ny_start": 510,      # 8:30 AM
        "ny_end": 660         # 11:00 AM (Refined for strictly ICT NY Killzone action)
    },
    "Strategy": {
        "enable_fvg": True,
        "enable_dol": True,
        "enable_smt": True,
        "enable_po3": True,
        "fvg_buffer_pct": 0.001,
        "min_rr": 1.2
    },
    "Risk": {
        "risk_per_trade_usd": 1000.0,
        "point_value": 50.0  # e.g., ES
    },
    "Backtest": {
        "initial_capital": 100000.0,
        "commission": 2.00,
        "slippage": 0.25
    }
}

def init_configs():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    default_path = os.path.join(CONFIG_DIR, DEFAULT_PROFILE)
    if not os.path.exists(default_path):
        # Write directly to avoid recursion
        with open(default_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)

    if not os.path.exists(ACTIVE_PROFILE_FILE):
        with open(ACTIVE_PROFILE_FILE, "w") as f:
            f.write(DEFAULT_PROFILE)

def get_active_profile_name():
    init_configs()
    try:
        with open(ACTIVE_PROFILE_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return DEFAULT_PROFILE

def set_active_profile(profile_name):
    init_configs()
    if not profile_name.endswith('.json'):
        profile_name += '.json'
    with open(ACTIVE_PROFILE_FILE, "w") as f:
        f.write(profile_name)

def load_profile(profile_name=None):
    init_configs()
    if not profile_name:
        profile_name = get_active_profile_name()

    if not profile_name.endswith('.json'):
        profile_name += '.json'

    path = os.path.join(CONFIG_DIR, profile_name)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading profile {profile_name}: {e}. Returning default.")
        return DEFAULT_CONFIG.copy()

def save_profile(profile_name, config_data):
    init_configs()
    if not profile_name.endswith('.json'):
        profile_name += '.json'
    path = os.path.join(CONFIG_DIR, profile_name)
    with open(path, "w") as f:
        json.dump(config_data, f, indent=4)

def list_profiles():
    init_configs()
    profiles = [f for f in os.listdir(CONFIG_DIR) if f.endswith('.json')]
    return sorted(profiles)

def delete_profile(profile_name):
    if not profile_name.endswith('.json'):
        profile_name += '.json'
    if profile_name == DEFAULT_PROFILE:
        return False # Protect default

    path = os.path.join(CONFIG_DIR, profile_name)
    if os.path.exists(path):
        os.remove(path)
        if get_active_profile_name() == profile_name:
            set_active_profile(DEFAULT_PROFILE)
        return True
    return False

if __name__ == "__main__":
    init_configs()
    print("Configs initialized.")
