"""
storage/paper.py
----------------
Simple persistence for the paper trading account.

Responsibilities:
- Load the account from storage/paper.json
- Save the account back to the same file
- Create a fresh $100,000 account if the file is missing or broken
- Provide convenience getters and a reset function

No buy/sell logic lives here. That will come later in logic/trading.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Absolute path to the JSON file (always next to this .py file)
_PAPER_PATH = Path(__file__).resolve().parent / "paper.json"


def _default_account() -> dict[str, Any]:
    """
    Return a brand-new paper account.
    Used when the file does not exist or is corrupt.
    """
    return {
        "cash": 100000.0,
        "positions": {},      # ticker → {"shares": float, "avg_cost": float}
        "history": [],        # list of trade records (filled by trading logic later)
    }


def load_paper_account() -> dict[str, Any]:
    """
    Load the paper trading account from disk.

    Behaviour
    ---------
    - If paper.json does not exist → create a fresh $100k account and save it.
    - If the file is corrupt or has the wrong shape → reset to a fresh account.
    - Always returns a dict with the three expected keys.

    Returns
    -------
    dict
        {
            "cash": float,
            "positions": dict,
            "history": list
        }
    """
    if not _PAPER_PATH.exists():
        print("[paper] paper.json not found — creating new account with $100,000.")
        account = _default_account()
        save_paper_account(account)
        return account

    try:
        with open(_PAPER_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Root value is not a dictionary")

        # Make sure the three required keys always exist
        data.setdefault("cash", 100000.0)
        data.setdefault("positions", {})
        data.setdefault("history", [])

        # Light type safety so later code never crashes on bad data
        if not isinstance(data["positions"], dict):
            data["positions"] = {}
        if not isinstance(data["history"], list):
            data["history"] = []

        data["cash"] = float(data["cash"])

        return data

    except Exception as e:
        print(f"[paper] Error reading paper.json ({e}) — resetting to fresh account.")
        account = _default_account()
        save_paper_account(account)
        return account


def save_paper_account(account: dict[str, Any]) -> None:
    """
    Write the entire account dictionary to storage/paper.json.

    The file is completely overwritten every time.
    This is intentional — it keeps the logic simple and predictable.
    """
    try:
        # Ensure the storage folder exists (safety net)
        _PAPER_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(_PAPER_PATH, "w", encoding="utf-8") as f:
            json.dump(account, f, indent=2, ensure_ascii=False)

    except Exception as e:
        # We never want a save failure to crash the whole CLI
        print(f"[paper] Failed to save paper.json: {e}")


# ------------------------------------------------------------------
# Convenience getters
# ------------------------------------------------------------------

def get_cash() -> float:
    """
    Return the current cash balance.

    Convenience wrapper around load_paper_account().
    """
    account = load_paper_account()
    return float(account.get("cash", 0.0))


def get_positions() -> dict[str, Any]:
    """
    Return the current positions dictionary.

    Example shape:
        {
            "AAPL": {"shares": 10.0, "avg_cost": 185.50},
            "MSFT": {"shares": 5.0,  "avg_cost": 420.00}
        }
    """
    account = load_paper_account()
    return account.get("positions", {})


def get_trade_history() -> list[dict[str, Any]]:
    """
    Return the list of past trades.

    Empty list until the trading logic starts recording trades.
    """
    account = load_paper_account()
    return account.get("history", [])


def reset_paper_account() -> None:
    """
    Reset the paper account to its starting state:
    - $100,000 cash
    - empty positions
    - empty trade history

    Useful for testing or when you want a clean slate.
    """
    account = _default_account()
    save_paper_account(account)
    print("[paper] Paper account has been reset to $100,000.")



# ------------------------------------------------------------------
# Quick manual test (run this file directly)
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("Testing storage/paper.py")
    print("=" * 50)

    # 1. Load (will create the file if it doesn't exist)
    print("\n1. Loading account ...")
    account = load_paper_account()
    print(f"   cash      : ${account['cash']:,.2f}")
    print(f"   positions : {account['positions']}")
    print(f"   history   : {account['history']}")

    # 2. Convenience getters
    print("\n2. Testing getters ...")
    print(f"   get_cash()          → ${get_cash():,.2f}")
    print(f"   get_positions()     → {get_positions()}")
    print(f"   get_trade_history() → {get_trade_history()}")

    # 3. Simulate a small change and save
    print("\n3. Simulating a change (adding fake position) ...")
    account = load_paper_account()
    account["cash"] = 95000.0
    account["positions"]["AAPL"] = {"shares": 10.0, "avg_cost": 185.50}
    account["history"].append({
        "ticker": "AAPL",
        "action": "BUY",
        "shares": 10,
        "price": 185.50,
        "note": "test trade"
    })
    save_paper_account(account)
    print("   Saved modified account.")

    print("\n4. Reloading to verify the change stuck ...")
    account = load_paper_account()
    print(f"   cash      : ${account['cash']:,.2f}")
    print(f"   positions : {account['positions']}")
    print(f"   history   : {account['history']}")

    # 5. Reset
    print("\n5. Resetting account ...")
    reset_paper_account()

    print("\n6. Final state after reset ...")
    account = load_paper_account()
    print(f"   cash      : ${account['cash']:,.2f}")
    print(f"   positions : {account['positions']}")
    print(f"   history   : {account['history']}")

    print("\n" + "=" * 50)
    print("All tests finished.")
    print("=" * 50)
