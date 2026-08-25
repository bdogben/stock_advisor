"""
logic/autonomous.py
-------------------
Fully autonomous paper-trading engine.

This module is the "brain" that:
1. Loads a universe of stocks
2. Runs advice on every ticker
3. Decides which trades to make (using the locked-in rules)
4. Executes those trades on the paper account
5. Returns a clear daily summary

Design goals (learning project):
- Reuse every existing module (prices, news, sentiment, advice, trading)
- Never crash — every external call and every missing-data case is handled
- Pure, readable functions that are easy to test and tweak
- Clear separation: analysis → decision → execution
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Make the project root importable no matter how this file is run
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.prices import get_current_price, get_history
from data.news import get_news
from logic.sentiment import analyze_news
from logic.advice import generate_advice
from logic.trading import buy, sell, get_account_summary
from storage.paper import get_positions


# ------------------------------------------------------------------
# Constants – the locked-in rules live here so they are easy to find
# ------------------------------------------------------------------
MAX_POSITIONS = 10
CASH_RESERVE_PCT = 0.15          # always keep at least 15% cash
HIGH_CONFIDENCE_PCT = 0.08       # up to 8% of portfolio for High confidence
MEDIUM_CONFIDENCE_PCT = 0.04     # up to 4% of portfolio for Medium confidence
# Only Medium and High confidence are allowed to trade
ALLOWED_CONFIDENCES = {"Medium", "High"}


# ------------------------------------------------------------------
# 1. load_universe()
# ------------------------------------------------------------------
def load_universe() -> list[str]:
    """
    Read the list of tickers from data/universe.txt.

    Behaviour
    ---------
    - One ticker per line.
    - Lines that start with # are treated as comments and ignored.
    - Blank lines are ignored.
    - Everything is upper-cased and stripped.
    - Duplicates are removed while preserving order of first appearance.
    - If the file is missing or unreadable → return an empty list
      (never raise an exception).

    Returns
    -------
    list[str]
        Clean list of ticker symbols, e.g. ["AAPL", "MSFT", "NVDA", ...]
    """
    # Locate the file relative to this module so it works from any cwd
    universe_path = Path(__file__).resolve().parent.parent / "data" / "universe.txt"

    if not universe_path.exists():
        print(f"[autonomous] universe.txt not found at {universe_path}")
        return []

    try:
        with open(universe_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[autonomous] Could not read universe.txt: {e}")
        return []

    tickers: list[str] = []
    seen: set[str] = set()

    for raw in lines:
        line = raw.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        # Take only the first token (in case someone adds a comment after the ticker)
        ticker = line.split()[0].upper()

        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)

    return tickers


# ------------------------------------------------------------------
# 2. analyze_universe()
# ------------------------------------------------------------------
def analyze_universe(
    tickers: list[str] | None = None,
    progress: bool = True,
) -> list[dict[str, Any]]:
    """
    Run the full advice pipeline on every ticker and return results
    ranked from best (highest score) to worst.

    Parameters
    ----------
    tickers : list[str] or None
        The list of symbols to analyse.
        If None, load_universe() is called automatically.
    progress : bool
        When True, print a simple progress line so you can see
        the scan is still working (useful for 200+ tickers).

    Returns
    -------
    list[dict]
        Each dict looks like:
        {
            "ticker": str,
            "action": "Buy" | "Hold" | "Sell" | "Watch",
            "confidence": "Low" | "Medium" | "High",
            "score": float,               # roughly -1.0 … +1.0
            "summary": str,
            "reasons": list[str],
            "current_price": float | None,
            "article_count": int,
        }
        Sorted by score descending (best first).
        Empty list if nothing could be analysed.
    """
    # 1. Decide which tickers to scan
    if tickers is None:
        tickers = load_universe()

    if not tickers:
        print("[autonomous] No tickers to analyse.")
        return []

    # 2. Snapshot current paper holdings once (used by generate_advice)
    #    Shape expected by generate_advice: {ticker: shares}
    raw_positions = get_positions()
    holdings = {
        t: float(pos.get("shares", 0))
        for t, pos in raw_positions.items()
    }

    results: list[dict[str, Any]] = []
    total = len(tickers)

    for i, ticker in enumerate(tickers, start=1):
        if progress:
            print(f"  [{i:3d}/{total}] {ticker} ...", end="", flush=True)

        try:
            # --- Price ---
            price = get_current_price(ticker)

            # --- History (list of closing prices, oldest → newest) ---
            price_history = None
            df = get_history(ticker, period="3mo")
            if df is not None and not df.empty and "Close" in df.columns:
                # Convert to plain Python floats so nothing downstream
                # has to deal with pandas types
                price_history = [float(x) for x in df["Close"].tolist()]

            # --- News + sentiment ---
            news = get_news(ticker, limit=6)
            sentiment = analyze_news(news)

            # --- Advice ---
            advice = generate_advice(
                ticker=ticker,
                sentiment=sentiment,
                current_price=price,
                price_history=price_history,
                holdings=holdings,
            )

            # Build a single clean record
            record = {
                "ticker": ticker,
                "action": advice.get("action", "Watch"),
                "confidence": advice.get("confidence", "Low"),
                "score": float(advice.get("score", 0.0)),
                "summary": advice.get("summary", ""),
                "reasons": advice.get("reasons", []),
                "current_price": price,          # may be None
                "article_count": int(sentiment.get("article_count", 0)),
            }
            results.append(record)

            if progress:
                conf = record["confidence"]
                score = record["score"]
                print(f"  {record['action']:5s}  conf={conf:6s}  score={score:+.2f}")

        except Exception as e:
            # Never let one bad ticker kill the whole scan
            if progress:
                print(f"  SKIPPED ({e})")
            continue

    # 3. Rank best → worst
    results.sort(key=lambda r: r["score"], reverse=True)

    if progress:
        print(f"\n[autonomous] Finished. {len(results)} tickers analysed.")

    return results


# ------------------------------------------------------------------
# 3. decide_trades()
# ------------------------------------------------------------------
def decide_trades(
    analysis: list[dict[str, Any]],
    account_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Apply the locked-in autonomous rules and return a list of proposed trades.

    This function is pure decision logic — it never buys or sells.
    It only looks at the ranked analysis and the current account state.

    Rules applied
    -------------
    - Only Medium or High confidence ideas are considered.
    - Max open positions = MAX_POSITIONS (10).
    - Always keep at least CASH_RESERVE_PCT (15%) in cash.
    - High confidence → size up to HIGH_CONFIDENCE_PCT (8%) of portfolio.
    - Medium confidence → size up to MEDIUM_CONFIDENCE_PCT (4%) of portfolio.
    - Sell only when rotating into a clearly better opportunity
      (we never sell just because a held stock is weak).

    Parameters
    ----------
    analysis : list[dict]
        Output of analyze_universe() — already ranked best → worst.
    account_summary : dict
        Output of get_account_summary().

    Returns
    -------
    list[dict]
        Proposed trades, each looking like:
        {
            "action": "BUY" | "SELL",
            "ticker": str,
            "shares": float,
            "price": float,
            "reason": str,
            "confidence": str,
            "score": float,
            "target_value": float,   # intended dollar amount (buys only)
        }
        Empty list if no trades should be made.
    """
    trades: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 0. Guard clauses
    # ------------------------------------------------------------------
    if not analysis:
        return trades

    cash = float(account_summary.get("cash", 0.0))
    positions = account_summary.get("positions", {}) or {}
    position_count = int(account_summary.get("position_count", len(positions)))

    # ------------------------------------------------------------------
    # 1. Build a quick price lookup from the analysis
    #    (for held positions that appear in the scan we already have prices)
    # ------------------------------------------------------------------
    price_map: dict[str, float] = {}
    score_map: dict[str, float] = {}
    for item in analysis:
        t = item.get("ticker", "")
        p = item.get("current_price")
        if t and p is not None and p > 0:
            price_map[t] = float(p)
        score_map[t] = float(item.get("score", 0.0))

    # For any held ticker missing a live price, fall back to avg_cost
    for t, pos in positions.items():
        if t not in price_map:
            avg = float(pos.get("avg_cost", 0.0))
            if avg > 0:
                price_map[t] = avg

    # ------------------------------------------------------------------
    # 2. Estimate total portfolio equity
    #    equity ≈ cash + market value of all open positions
    # ------------------------------------------------------------------
    market_value = 0.0
    for t, pos in positions.items():
        shares = float(pos.get("shares", 0.0))
        px = price_map.get(t, float(pos.get("avg_cost", 0.0)))
        market_value += shares * px

    equity = cash + market_value
    if equity <= 0:
        # Safety: nothing to work with
        return trades

    # Minimum cash we must keep
    min_cash = equity * CASH_RESERVE_PCT
    # Cash available for new buys (never touch the reserve)
    available_cash = max(0.0, cash - min_cash)

    # ------------------------------------------------------------------
    # 3. Identify candidate buys
    #    - Must be Medium or High confidence
    #    - Must have a usable price
    #    - Prefer action == "Buy", but also accept strong positive scores
    # ------------------------------------------------------------------
    candidates: list[dict[str, Any]] = []
    for item in analysis:
        conf = item.get("confidence", "Low")
        action = item.get("action", "Watch")
        score = float(item.get("score", 0.0))
        ticker = item.get("ticker", "")
        price = item.get("current_price")

        if conf not in ALLOWED_CONFIDENCES:
            continue
        if price is None or price <= 0:
            continue
        # Only consider Buy ideas (or very strong positive scores)
        if action != "Buy" and score < 0.30:
            continue
        # Skip if we already hold this ticker (no averaging-up in this version)
        if ticker in positions:
            continue

        candidates.append(item)

    # candidates are already sorted best → worst because analysis is ranked

    # ------------------------------------------------------------------
    # 4. Identify which held positions are the weakest
    #    (we only sell if we need a slot or capital for a clearly better idea)
    # ------------------------------------------------------------------
    held_scores: list[tuple[str, float, float]] = []  # (ticker, score, shares)
    for t, pos in positions.items():
        shares = float(pos.get("shares", 0.0))
        if shares <= 0:
            continue
        sc = score_map.get(t, 0.0)  # 0.0 if the ticker wasn't in this scan
        held_scores.append((t, sc, shares))

    # Sort weakest first (lowest score)
    held_scores.sort(key=lambda x: x[1])

    # ------------------------------------------------------------------
    # 5. Rotation logic
    #    If we are at (or near) max positions and have a strong new candidate,
    #    consider selling the weakest held position to free a slot.
    # ------------------------------------------------------------------
    ROTATION_SCORE_GAP = 0.20   # new idea must be at least this much better

    open_slots = MAX_POSITIONS - position_count

    if open_slots <= 0 and candidates and held_scores:
        best_new = candidates[0]
        weakest_held = held_scores[0]
        new_score = float(best_new.get("score", 0.0))
        old_score = weakest_held[1]
        old_ticker = weakest_held[0]
        old_shares = weakest_held[2]

        if new_score - old_score >= ROTATION_SCORE_GAP:
            # Propose a full sell of the weakest position
            sell_price = price_map.get(old_ticker)
            if sell_price and sell_price > 0 and old_shares > 0:
                trades.append({
                    "action": "SELL",
                    "ticker": old_ticker,
                    "shares": old_shares,
                    "price": sell_price,
                    "reason": (
                        f"Rotate out of {old_ticker} (score {old_score:+.2f}) "
                        f"to free a slot for stronger opportunity "
                        f"{best_new['ticker']} (score {new_score:+.2f})"
                    ),
                    "confidence": best_new.get("confidence", ""),
                    "score": new_score,
                    "target_value": 0.0,
                })
                # After this sell we will have one open slot and more cash
                open_slots = 1
                # Roughly free the market value for later buy calculations
                available_cash += old_shares * sell_price

    # ------------------------------------------------------------------
    # 6. Decide buys
    #    Walk candidates from best → worst and allocate capital
    #    while respecting position limit and cash reserve.
    # ------------------------------------------------------------------
    for item in candidates:
        if open_slots <= 0:
            break
        if available_cash <= 0:
            break

        ticker = item["ticker"]
        price = float(item["current_price"])
        conf = item["confidence"]
        score = float(item["score"])

        # Max dollar amount we are allowed to put into this name
        if conf == "High":
            max_alloc = equity * HIGH_CONFIDENCE_PCT
        else:
            max_alloc = equity * MEDIUM_CONFIDENCE_PCT

        # Never spend more than we actually have available
        dollar_amount = min(max_alloc, available_cash)

        # How many whole shares can we buy?
        shares = int(dollar_amount // price)  # whole shares only (simple)
        if shares < 1:
            continue  # not enough capital for even one share

        cost = shares * price

        trades.append({
            "action": "BUY",
            "ticker": ticker,
            "shares": float(shares),
            "price": price,
            "reason": (
                f"{conf} confidence Buy (score {score:+.2f}). "
                f"Allocating ~{cost / equity * 100:.1f}% of portfolio."
            ),
            "confidence": conf,
            "score": score,
            "target_value": round(cost, 2),
        })

        # Update running state so the next candidate sees the new limits
        available_cash -= cost
        open_slots -= 1

    return trades


# ------------------------------------------------------------------
# 4. execute_trades()
# ------------------------------------------------------------------
def execute_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Take the list of proposed trades from decide_trades() and actually
    execute them on the paper account using the existing buy() / sell().

    Parameters
    ----------
    trades : list[dict]
        Output of decide_trades(). Each dict must contain at least:
        "action", "ticker", "shares", "price".

    Returns
    -------
    list[dict]
        One result per attempted trade. Each result looks like:
        {
            "success": bool,
            "action": "BUY" | "SELL",
            "ticker": str,
            "shares": float,
            "price": float,
            "message": str,          # from buy()/sell()
            "reason": str,           # original reason from decide_trades
        }
        Empty list if nothing was attempted.
    """
    results: list[dict[str, Any]] = []

    if not trades:
        return results

    for trade in trades:
        action = str(trade.get("action", "")).upper()
        ticker = str(trade.get("ticker", "")).upper()
        shares = float(trade.get("shares", 0))
        price = float(trade.get("price", 0))
        reason = trade.get("reason", "")

        # Basic validation so we never call buy/sell with garbage
        if action not in ("BUY", "SELL") or not ticker or shares <= 0 or price <= 0:
            results.append({
                "success": False,
                "action": action,
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "message": "Invalid trade data — skipped.",
                "reason": reason,
            })
            continue

        try:
            if action == "BUY":
                outcome = buy(ticker, shares, price)
            else:
                outcome = sell(ticker, shares, price)

            results.append({
                "success": bool(outcome.get("success", False)),
                "action": action,
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "message": outcome.get("message", ""),
                "reason": reason,
            })

        except Exception as e:
            # Absolute last-resort safety net
            results.append({
                "success": False,
                "action": action,
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "message": f"Unexpected error: {e}",
                "reason": reason,
            })

    return results


# ------------------------------------------------------------------
# 5. run_daily_scan()  – the main entry point
# ------------------------------------------------------------------
def run_daily_scan(
    tickers: list[str] | None = None,
    progress: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Full autonomous daily cycle.

    Steps
    -----
    1. Load (or accept) the universe
    2. Analyse every ticker → ranked list
    3. Snapshot the paper account
    4. Decide which trades to make
    5. Execute them (unless dry_run=True)
    6. Return a clear summary dictionary

    Parameters
    ----------
    tickers : list[str] or None
        Optional subset of the universe (useful for testing).
        If None, the full universe is used.
    progress : bool
        Print progress lines while analysing.
    dry_run : bool
        If True, only analyse + decide — do NOT execute any trades.
        Perfect for inspecting what the system *would* do.

    Returns
    -------
    dict
        {
            "universe_size": int,
            "analysed": int,
            "top_ideas": list[dict],      # top 5 by score
            "proposed_trades": list[dict],
            "executed": list[dict],       # empty if dry_run
            "account_before": dict,
            "account_after": dict,
            "message": str,
        }
    """
    print("\n" + "=" * 60)
    print("AUTONOMOUS DAILY SCAN")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Universe
    # ------------------------------------------------------------------
    if tickers is None:
        tickers = load_universe()

    universe_size = len(tickers)
    print(f"Universe : {universe_size} tickers")

    if universe_size == 0:
        return {
            "universe_size": 0,
            "analysed": 0,
            "top_ideas": [],
            "proposed_trades": [],
            "executed": [],
            "account_before": get_account_summary(),
            "account_after": get_account_summary(),
            "message": "Empty universe — nothing to do.",
        }

    # ------------------------------------------------------------------
    # 2. Analyse
    # ------------------------------------------------------------------
    print("\nAnalysing universe ...")
    analysis = analyze_universe(tickers=tickers, progress=progress)

    top_ideas = analysis[:5]  # already sorted best → worst

    if top_ideas:
        print("\nTop ideas:")
        for r in top_ideas:
            price_str = f"${r['current_price']:.2f}" if r["current_price"] else "N/A"
            print(
                f"  {r['ticker']:6s}  {r['action']:5s}  "
                f"conf={r['confidence']:6s}  score={r['score']:+.2f}  "
                f"price={price_str}"
            )

    # ------------------------------------------------------------------
    # 3. Account snapshot (before)
    # ------------------------------------------------------------------
    account_before = get_account_summary()
    print(f"\nAccount before : cash ${account_before['cash']:,.2f}  |  "
          f"positions {account_before['position_count']}")

    # ------------------------------------------------------------------
    # 4. Decide
    # ------------------------------------------------------------------
    proposed = decide_trades(analysis, account_before)

    if not proposed:
        print("\nNo trades proposed today.")
        return {
            "universe_size": universe_size,
            "analysed": len(analysis),
            "top_ideas": top_ideas,
            "proposed_trades": [],
            "executed": [],
            "account_before": account_before,
            "account_after": account_before,
            "message": "No trades met the autonomous rules.",
        }

    print(f"\nProposed {len(proposed)} trade(s):")
    for t in proposed:
        print(
            f"  {t['action']:4s}  {t['shares']:.0f} {t['ticker']} "
            f"@ ${t['price']:.2f}  →  {t['reason']}"
        )

    # ------------------------------------------------------------------
    # 5. Execute (or skip if dry_run)
    # ------------------------------------------------------------------
    executed: list[dict[str, Any]] = []

    if dry_run:
        print("\n[DRY RUN] Trades were NOT executed.")
        account_after = account_before
        message = f"Dry run complete. {len(proposed)} trade(s) would have been executed."
    else:
        print("\nExecuting trades ...")
        executed = execute_trades(proposed)

        for r in executed:
            status = "OK" if r["success"] else "FAIL"
            print(f"  [{status}] {r['action']} {r['shares']:.0f} {r['ticker']} — {r['message']}")

        account_after = get_account_summary()
        successes = sum(1 for r in executed if r["success"])
        message = f"Executed {successes}/{len(executed)} trade(s)."

    # ------------------------------------------------------------------
    # 6. Final report
    # ------------------------------------------------------------------
    print(f"\nAccount after  : cash ${account_after['cash']:,.2f}  |  "
          f"positions {account_after['position_count']}")

    if account_after.get("positions"):
        print("Open positions:")
        for t, pos in account_after["positions"].items():
            print(f"  {t}: {pos['shares']} shares @ avg ${pos['avg_cost']:.2f}")

    print("=" * 60)
    print(message)
    print("=" * 60)

    return {
        "universe_size": universe_size,
        "analysed": len(analysis),
        "top_ideas": top_ideas,
        "proposed_trades": proposed,
        "executed": executed,
        "account_before": account_before,
        "account_after": account_after,
        "message": message,
    }


# ------------------------------------------------------------------
# Quick manual test (run this file directly)
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Use a tiny subset + dry_run so the test is fast and safe
    universe = load_universe()
    sample_tickers = universe[:6]

    print("Running dry-run on a 6-ticker sample ...")
    result = run_daily_scan(
        tickers=sample_tickers,
        progress=True,
        dry_run=True,          # ← no real trades
    )

    print("\nReturned summary keys:", list(result.keys()))
    print("Message:", result["message"])
