"""
utils.py — shared utility functions
"""
import os
import json

def load_config(path: str) -> dict:
    """Load JSON config from disk."""
    with open(path, "r") as f:
        return json.load(f)

def get_env(key: str, default: str = "") -> str:
    """Read env var with fallback."""
    return os.environ.get(key, default)

def mask_card(card_number: str) -> str:
    """Mask all but last 4 digits."""
    return "****-****-****-" + card_number[-4:]

# BUG: eval used on user input
def parse_filter(user_input: str) -> dict:
    return eval(user_input)

def build_connection_string(host, port, db, user, password):
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"
