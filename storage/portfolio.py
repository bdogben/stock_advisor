"""
portfolio.py – Simple JSON-based portfolio storage.

Responsibilities:
- Load the portfolio from disk
- Save the portfolio to disk
- (Later) add / remove / list holdings
"""

import json
from pathlib import Path
from typing import Dict, Any

# Path to the JSON file (same folder as this module)
PORTFOLIO_FILE = Path(__file__).parent / "portfolio.json"


def load_portfolio() -> Dict[str, Any]:
    """
    Load the portfolio from storage/portfolio.json.
    If the file does not exist or is empty/corrupt, return a fresh empty portfolio.
    """
    if not PORTFOLIO_FILE.exists():
        # First run – no file yet
        return {"holdings": {}}

    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Basic safety check – make sure the expected key exists
        if not isinstance(data, dict) or "holdings" not in data:
            print("Warning: portfolio.json looks invalid. Starting with empty portfolio.")
            return {"holdings": {}}

        return data

    except (json.JSONDecodeError, OSError) as e:
        # File is corrupted or unreadable
        print(f"Warning: could not read portfolio.json ({e}). Starting with empty portfolio.")
        return {"holdings": {}}


def save_portfolio(portfolio: Dict[str, Any]) -> None:
    """
    Save the entire portfolio dictionary to storage/portfolio.json.
    Creates the file if it does not exist.
    """
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2)
    except OSError as e:
        print(f"Error: could not write portfolio.json ({e})")

def add_holding(ticker: str, shares: float, cost_basis: float) -> None:
    """
    Add a new holding or overwrite an existing one.

    Args:
        ticker: Stock symbol (e.g. "AAPL")
        shares: Number of shares
        cost_basis: Average cost per share
    """
    # Normalize ticker to uppercase
    ticker = ticker.upper().strip()

    # Basic validation
    if not ticker:
        print("Error: ticker cannot be empty")
        return
    if shares <= 0:
        print("Error: shares must be positive")
        return
    if cost_basis < 0:
        print("Error: cost_basis cannot be negative")
        return

    # Load → modify → save
    portfolio = load_portfolio()
    portfolio["holdings"][ticker] = {
        "shares": float(shares),
        "cost_basis": float(cost_basis)
    }
    save_portfolio(portfolio)
    print(f"Added/updated {ticker}: {shares} shares @ ${cost_basis:.2f}")


def remove_holding(ticker: str) -> bool:
    """
    Remove a holding from the portfolio.

    Args:
        ticker: Stock symbol to remove

    Returns:
        True if the holding was removed, False if it did not exist
    """
    ticker = ticker.upper().strip()

    if not ticker:
        print("Error: ticker cannot be empty")
        return False

    portfolio = load_portfolio()

    if ticker not in portfolio["holdings"]:
        print(f"{ticker} not found in portfolio")
        return False

    # Delete the holding
    del portfolio["holdings"][ticker]
    save_portfolio(portfolio)
    print(f"Removed {ticker}")
    return True


def get_holdings() -> dict:
    """
    Return only the holdings dictionary.
    Example return value:
        {
            "AAPL": {"shares": 12.0, "cost_basis": 180.25},
            "MSFT": {"shares": 5.0, "cost_basis": 410.0}
        }
    """
    portfolio = load_portfolio()
    return portfolio.get("holdings", {})
