"""
logic/trading.py
----------------
Paper-trading rules: buy and sell.

Responsibilities
----------------
- Validate a trade request
- Update cash and positions (weighted-average cost basis)
- Record the trade in history
- Persist the account via storage/paper.py
- Always return a clear result dictionary (never raise)

This module contains NO price-fetching and NO sentiment logic.
The caller supplies the price.  That keeps the code pure and easy to test.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone
from typing import Any

from storage.paper import load_paper_account, save_paper_account

# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _make_result(
    success: bool,
    message: str,
    account: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the standard result dictionary that every public function returns.

    Always includes the current account so the caller can inspect state
    even after a failed trade.
    """
    if account is None:
        account = load_paper_account()

    return {
        "success": success,
        "message": message,
        "account": account,
    }


def _normalize_ticker(ticker: str) -> str:
    """
    Clean and standardize a ticker symbol.

    - Strip whitespace
    - Convert to uppercase
    - Return empty string if the result is empty (caller will reject it)
    """
    if not isinstance(ticker, str):
        return ""
    return ticker.strip().upper()


def _validate_trade_inputs(
    ticker: str,
    shares: float,
    price: float,
) -> str | None:
    """
    Shared validation for both buy() and sell().

    Returns
    -------
    None  if everything looks good
    str   human-readable error message if something is wrong
    """
    if not ticker:
        return "Ticker cannot be empty."

    try:
        shares = float(shares)
        price = float(price)
    except (TypeError, ValueError):
        return "Shares and price must be numbers."

    if shares <= 0:
        return "Shares must be greater than zero."

    if price <= 0:
        return "Price must be greater than zero."

    return None  # all good


# ------------------------------------------------------------------
# Public API (stubs for now – we will fill these in next steps)
# ------------------------------------------------------------------

def buy(ticker: str, shares: float, price: float) -> dict[str, Any]:
    """
    Attempt to buy `shares` of `ticker` at `price`.

    Steps
    -----
    1. Normalize and validate inputs
    2. Load the current paper account
    3. Check that there is enough cash
    4. Update cash and positions (weighted-average cost)
    5. Record the trade in history
    6. Save the account
    7. Return a clear result dictionary
    """
    # 1. Normalize ticker
    ticker = _normalize_ticker(ticker)

    # 2. Validate inputs
    error = _validate_trade_inputs(ticker, shares, price)
    if error:
        return _make_result(False, error)

    # Make sure we are working with floats
    shares = float(shares)
    price = float(price)
    cost = shares * price

    # 3. Load current account
    account = load_paper_account()
    cash = float(account.get("cash", 0.0))
    positions = account.get("positions", {})

    # 4. Enough cash?
    if cost > cash:
        return _make_result(
            False,
            f"Not enough cash. Need ${cost:,.2f}, have ${cash:,.2f}.",
            account,
        )

    # 5. Update cash
    account["cash"] = cash - cost

    # 6. Update (or create) the position with weighted-average cost
    if ticker in positions:
        old = positions[ticker]
        old_shares = float(old.get("shares", 0.0))
        old_avg = float(old.get("avg_cost", 0.0))

        new_shares = old_shares + shares
        new_avg = ((old_shares * old_avg) + (shares * price)) / new_shares

        positions[ticker] = {
            "shares": new_shares,
            "avg_cost": round(new_avg, 4),   # keep 4 decimal places
        }
    else:
        positions[ticker] = {
            "shares": shares,
            "avg_cost": price,
        }

    account["positions"] = positions

    # 7. Record the trade
    trade = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "ticker": ticker,
        "action": "BUY",
        "shares": shares,
        "price": price,
        "total": round(cost, 2),
        "cash_after": round(account["cash"], 2),
    }
    account.setdefault("history", []).append(trade)

    # 8. Save
    save_paper_account(account)

    # 9. Success
    msg = (
        f"Bought {shares} shares of {ticker} at ${price:,.2f} "
        f"(total ${cost:,.2f}). Cash left: ${account['cash']:,.2f}."
    )
    return _make_result(True, msg, account)


def sell(ticker: str, shares: float, price: float) -> dict[str, Any]:
    """
    Attempt to sell `shares` of `ticker` at `price`.

    Steps
    -----
    1. Normalize and validate inputs
    2. Load the current paper account
    3. Check that the position exists and has enough shares
    4. Update cash and positions
    5. Record the trade in history
    6. Save the account
    7. Return a clear result dictionary
    """
    # 1. Normalize ticker
    ticker = _normalize_ticker(ticker)

    # 2. Validate inputs
    error = _validate_trade_inputs(ticker, shares, price)
    if error:
        return _make_result(False, error)

    shares = float(shares)
    price = float(price)
    proceeds = shares * price

    # 3. Load current account
    account = load_paper_account()
    cash = float(account.get("cash", 0.0))
    positions = account.get("positions", {})

    # 4. Do we own this ticker?
    if ticker not in positions:
        return _make_result(
            False,
            f"You do not own any shares of {ticker}.",
            account,
        )

    current_shares = float(positions[ticker].get("shares", 0.0))

    # 5. Enough shares?
    if shares > current_shares:
        return _make_result(
            False,
            f"Not enough shares. Trying to sell {shares}, but only own {current_shares}.",
            account,
        )

    # 6. Update cash
    account["cash"] = cash + proceeds

    # 7. Update (or remove) the position
    remaining = current_shares - shares

    if remaining > 0:
        # Keep the same average cost
        positions[ticker]["shares"] = remaining
    else:
        # Sold everything — remove the position
        del positions[ticker]

    account["positions"] = positions

    # 8. Record the trade
    trade = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "ticker": ticker,
        "action": "SELL",
        "shares": shares,
        "price": price,
        "total": round(proceeds, 2),
        "cash_after": round(account["cash"], 2),
    }
    account.setdefault("history", []).append(trade)

    # 9. Save
    save_paper_account(account)

    # 10. Success
    msg = (
        f"Sold {shares} shares of {ticker} at ${price:,.2f} "
        f"(total ${proceeds:,.2f}). Cash now: ${account['cash']:,.2f}."
    )
    return _make_result(True, msg, account)


def get_account_summary() -> dict[str, Any]:
    """
    Return a clean snapshot of the paper trading account.

    Includes:
    - current cash
    - all open positions
    - total cost basis (money currently invested)
    - number of open positions
    - number of trades in history
    """
    account = load_paper_account()

    cash = float(account.get("cash", 0.0))
    positions = account.get("positions", {})
    history = account.get("history", [])

    # Calculate total cost basis (shares × avg_cost for every position)
    cost_basis = 0.0
    for pos in positions.values():
        shares = float(pos.get("shares", 0.0))
        avg_cost = float(pos.get("avg_cost", 0.0))
        cost_basis += shares * avg_cost

    return {
        "cash": round(cash, 2),
        "positions": positions,
        "cost_basis": round(cost_basis, 2),
        "position_count": len(positions),
        "trade_count": len(history),
    }
