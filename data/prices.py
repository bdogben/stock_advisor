"""
data/prices.py
--------------
Responsible for fetching stock price data using yfinance.
All functions return None on failure so the rest of the app
can handle missing data gracefully.
"""

from typing import Optional
import pandas as pd
import yfinance as yf

def get_current_price(ticker: str) -> float | None:
    """
    Fetch the most recent price for a given ticker.

    Returns:
        float  – the latest available price, or
        None   – if anything goes wrong (invalid ticker, network issue, etc.)
    """
    try:
        # Clean the input a bit so " aapl " or "aapl" both work
        ticker = ticker.strip().upper()
        if not ticker:
            return None

        stock = yf.Ticker(ticker)

        # Preferred modern way – fast and reliable
        price = getattr(stock.fast_info, "last_price", None)

        # Fallback if fast_info doesn't have it
        if price is None:
            info = stock.info
            price = (
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or info.get("previousClose")
            )

        # Final safety check
        if price is None:
            return None

        return float(price)

    except Exception:
        # Catch *any* error (network, missing data, Yahoo changes, etc.)
        # and return None so the rest of the app stays stable
        return None




def get_history(ticker: str, period: str = "6mo") -> pd.DataFrame | None:
    """
    Fetch historical daily price data for a ticker.

    Args:
        ticker: Stock symbol (e.g. "AAPL", "MSFT")
        period: How far back to look. Common valid values:
                "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
                Default is "6mo" (six months).

    Returns:
        A pandas DataFrame with columns like:
            Open, High, Low, Close, Volume, Dividends, Stock Splits
        or None if anything goes wrong.
    """
    try:
        # Clean the ticker the same way we did in get_current_price
        ticker = ticker.strip().upper()
        if not ticker:
            return None

        stock = yf.Ticker(ticker)

        # Ask for historical data
        # progress=False hides the download progress bar (cleaner for a CLI app)
        # auto_adjust=True adjusts prices for splits and dividends (usually what you want)
        df = stock.history(
            period=period,
            auto_adjust=True
        )

        # yfinance returns an empty DataFrame when the ticker is invalid
        # or when there is simply no data for that period
        if df is None or df.empty:
            return None

        return df

    except Exception:
        return None
