"""
main.py – Simple CLI for the Stock Advisor learning project.

This is the entry point. It shows a menu and calls the existing modules.
No business logic lives here – we only orchestrate the other files.
"""

from data.prices import get_current_price, get_history
from data.news import get_news
from logic.sentiment import analyze_news
from logic.advice import generate_advice
from logic.trading import buy, sell, get_account_summary
from logic.autonomous import run_daily_scan
from storage.portfolio import get_holdings


# ------------------------------------------------------------------
# Menu display
# ------------------------------------------------------------------
def show_menu() -> None:
    """Print the main menu."""
    print()
    print("===== Stock Advisor =====")
    print("1. Get Price + Advice")
    print("2. News & Sentiment")
    print("3. Paper Trading (Buy / Sell / Summary)")
    print("4. View Real Portfolio")
    print("5. Run Autonomous Daily Scan")
    print("0. Exit")
    print("=========================")


# ------------------------------------------------------------------
# Option 1 – Get Price + Advice
# ------------------------------------------------------------------
def option_get_price_and_advice() -> None:
    """Ask for a ticker → show current price + advice."""
    ticker = input("Enter ticker symbol: ").strip().upper()

    if not ticker:
        print("Ticker cannot be empty.")
        return

    print(f"\nLooking up {ticker}...")

    # Current price
    price = get_current_price(ticker)
    if price is not None:
        print(f"Current price : ${price:.2f}")
    else:
        print("Current price : could not be fetched")

    # Price history → list of closing prices (oldest → newest)
    price_history = None
    df = get_history(ticker, period="3mo")
    if df is not None and not df.empty and "Close" in df.columns:
        price_history = df["Close"].tolist()

    # News + sentiment
    news = get_news(ticker, limit=8)
    sentiment = analyze_news(news)

    # Simple holdings dict that generate_advice expects (ticker → shares)
    raw_holdings = get_holdings()
    holdings = {
        t: data.get("shares", 0)
        for t, data in raw_holdings.items()
    }

    # Generate advice
    advice = generate_advice(
        ticker=ticker,
        sentiment=sentiment,
        current_price=price,
        price_history=price_history,
        holdings=holdings,
    )

    # Display
    print("\n----- Advice -----")
    print(f"Action     : {advice['action']}")
    print(f"Confidence : {advice['confidence']}")
    print(f"Score      : {advice['score']:+.2f}")
    print(f"Summary    : {advice['summary']}")
    print("\nReasons:")
    for reason in advice["reasons"]:
        print(f"  • {reason}")
    print("------------------")


# ------------------------------------------------------------------
# Option 2 – News & Sentiment
# ------------------------------------------------------------------
def option_news_and_sentiment() -> None:
    """Ask for a ticker → show news + overall sentiment."""
    ticker = input("Enter ticker symbol: ").strip().upper()

    if not ticker:
        print("Ticker cannot be empty.")
        return

    print(f"\nFetching news for {ticker}...")

    news = get_news(ticker, limit=8)

    if not news:
        print("No relevant news found (or an error occurred).")
        return

    sentiment = analyze_news(news)

    print("\n----- Sentiment Summary -----")
    print(f"Overall score : {sentiment['score']:+.3f}")
    print(f"Label         : {sentiment['label']}")
    print(f"Articles used : {sentiment['article_count']}")
    print("-----------------------------")

    print("\nRecent articles:")
    for i, article in enumerate(sentiment["articles"], start=1):
        print(f"\n{i}. {article['title']}")
        print(f"   Sentiment: {article['label']} ({article['score']:+.3f})")


# ------------------------------------------------------------------
# Option 3 – Paper Trading submenu
# ------------------------------------------------------------------
def option_paper_trading() -> None:
    """Simple paper trading submenu (Buy / Sell / Summary)."""
    while True:
        print()
        print("----- Paper Trading -----")
        print("1. Buy")
        print("2. Sell")
        print("3. View Summary")
        print("0. Back to main menu")
        print("-------------------------")

        choice = input("Enter choice: ").strip()

        if choice == "1":
            _paper_buy()
        elif choice == "2":
            _paper_sell()
        elif choice == "3":
            _paper_summary()
        elif choice == "0":
            break
        else:
            print("Invalid choice. Please enter 0, 1, 2 or 3.")


def _paper_buy() -> None:
    """Handle a paper buy."""
    ticker = input("Ticker to buy: ").strip().upper()
    if not ticker:
        print("Ticker cannot be empty.")
        return

    price = get_current_price(ticker)
    if price is None:
        print(f"Could not fetch current price for {ticker}.")
        return

    print(f"Current price of {ticker}: ${price:.2f}")

    shares_str = input("Number of shares to buy: ").strip()
    try:
        shares = float(shares_str)
    except ValueError:
        print("Please enter a valid number.")
        return

    result = buy(ticker, shares, price)
    print(result["message"])


def _paper_sell() -> None:
    """Handle a paper sell."""
    ticker = input("Ticker to sell: ").strip().upper()
    if not ticker:
        print("Ticker cannot be empty.")
        return

    price = get_current_price(ticker)
    if price is None:
        print(f"Could not fetch current price for {ticker}.")
        return

    print(f"Current price of {ticker}: ${price:.2f}")

    shares_str = input("Number of shares to sell: ").strip()
    try:
        shares = float(shares_str)
    except ValueError:
        print("Please enter a valid number.")
        return

    result = sell(ticker, shares, price)
    print(result["message"])


def _paper_summary() -> None:
    """Show a simple paper account summary."""
    summary = get_account_summary()

    print("\n----- Paper Account Summary -----")
    print(f"Cash            : ${summary['cash']:,.2f}")
    print(f"Cost basis      : ${summary['cost_basis']:,.2f}")
    print(f"Open positions  : {summary['position_count']}")
    print(f"Trades so far   : {summary['trade_count']}")

    if summary["positions"]:
        print("\nPositions:")
        for ticker, pos in summary["positions"].items():
            shares = pos.get("shares", 0)
            avg_cost = pos.get("avg_cost", 0)
            print(f"  {ticker}: {shares} shares @ ${avg_cost:.2f}")
    else:
        print("\nNo open positions.")
    print("---------------------------------")


# ------------------------------------------------------------------
# Option 4 – View Real Portfolio
# ------------------------------------------------------------------
def option_view_portfolio() -> None:
    """Show the real portfolio holdings."""
    holdings = get_holdings()

    print("\n----- Real Portfolio -----")

    if not holdings:
        print("Portfolio is empty.")
    else:
        for ticker, data in holdings.items():
            shares = data.get("shares", 0)
            cost_basis = data.get("cost_basis", 0)
            print(f"{ticker}: {shares} shares @ ${cost_basis:.2f}")

    print("--------------------------")


# ------------------------------------------------------------------
# Option 5 – Autonomous Daily Scan
# ------------------------------------------------------------------
def option_autonomous_scan() -> None:
    """
    Run the full autonomous paper-trading cycle.

    Asks the user whether this should be a dry run (safe preview)
    or a live run (actually executes the trades).
    """
    print("\n----- Autonomous Daily Scan -----")
    print("This will analyse the entire universe and decide trades")
    print("according to the locked-in rules (max 10 positions,")
    print("15% cash reserve, Medium/High confidence only, etc.).")
    print()
    print("1. Dry run  (analyse + propose only – no trades)")
    print("2. Live run (analyse + propose + execute trades)")
    print("0. Cancel")
    print("---------------------------------")

    choice = input("Enter choice: ").strip()

    if choice == "0":
        print("Cancelled.")
        return
    if choice not in ("1", "2"):
        print("Invalid choice. Please enter 0, 1 or 2.")
        return

    dry_run = choice == "1"

    if dry_run:
        print("\nStarting DRY RUN (no trades will be executed)...")
    else:
        print("\nStarting LIVE RUN (trades WILL be executed on the paper account)...")
        confirm = input("Type YES to confirm: ").strip()
        if confirm != "YES":
            print("Live run cancelled.")
            return

    # Call the autonomous engine
    result = run_daily_scan(dry_run=dry_run)

    # Extra readable summary from the returned dict
    # (run_daily_scan already prints a lot; this just makes the final
    # numbers easy to spot at a glance)
    print("\n===== SCAN SUMMARY =====")
    print(f"Universe size     : {result['universe_size']}")
    print(f"Tickers analysed  : {result['analysed']}")
    print(f"Proposed trades   : {len(result['proposed_trades'])}")
    print(f"Executed trades   : {len(result['executed'])}")
    print(f"Message           : {result['message']}")
    print()

    before = result["account_before"]
    after = result["account_after"]
    print("Account before:")
    print(f"  Cash      : ${before['cash']:,.2f}")
    print(f"  Positions : {before['position_count']}")
    print("Account after:")
    print(f"  Cash      : ${after['cash']:,.2f}")
    print(f"  Positions : {after['position_count']}")
    print("========================")


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------
def main() -> None:
    """Run the interactive menu until the user chooses to exit."""
    print("Welcome to Stock Advisor (learning project)")

    while True:
        show_menu()
        choice = input("Enter choice: ").strip()

        if choice == "1":
            option_get_price_and_advice()
        elif choice == "2":
            option_news_and_sentiment()
        elif choice == "3":
            option_paper_trading()
        elif choice == "4":
            option_view_portfolio()
        elif choice == "5":
            option_autonomous_scan()
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 0, 1, 2, 3, 4 or 5.")


# ------------------------------------------------------------------
# Standard Python entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    main()
