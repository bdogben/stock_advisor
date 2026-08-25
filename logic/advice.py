"""
logic/advice.py
---------------
Turns sentiment + basic price data into a simple, educational trading suggestion.

Main function:
    generate_advice()  → returns a clear advice dictionary

Also provides:
    get_advice_settings()    → see current weights / thresholds
    update_advice_settings() → change them at runtime

Design goals (learning project):
- Pure decision logic (receives data, never fetches it)
- Simple, transparent scoring (sentiment + price momentum)
- Tunable settings via a dict (easy to experiment)
- Never crashes — degrades gracefully when data is missing
- Easy to read and tweak
"""

from typing import Any


# ------------------------------------------------------------------
# Tunable settings (the single source of truth)
# ------------------------------------------------------------------
# Change these defaults here, or call update_advice_settings() at runtime.
_ADVICE_SETTINGS: dict[str, float] = {
    "sentiment_weight": 0.60,
    "price_weight": 0.40,
    "buy_threshold": 0.25,
    "sell_threshold": -0.25,
}


def get_advice_settings() -> dict[str, float]:
    """
    Return a *copy* of the current advice settings.

    Using a copy prevents accidental modification of the live dict.
    """
    return _ADVICE_SETTINGS.copy()


def update_advice_settings(
    sentiment_weight: float | None = None,
    price_weight: float | None = None,
    buy_threshold: float | None = None,
    sell_threshold: float | None = None,
) -> dict[str, float]:
    """
    Update one or more advice settings at runtime.

    - Only the parameters you pass are changed.
    - Weights are automatically normalized so they always sum to 1.0.
    - Thresholds are left as-is (you control the values).
    - Returns the new full settings dictionary.

    Examples
    --------
    update_advice_settings(sentiment_weight=0.7)          # price becomes 0.3
    update_advice_settings(buy_threshold=0.35, sell_threshold=-0.35)
    """
    # --- Update weights if provided ---
    if sentiment_weight is not None or price_weight is not None:
        # Start from current values
        s = sentiment_weight if sentiment_weight is not None else _ADVICE_SETTINGS["sentiment_weight"]
        p = price_weight if price_weight is not None else _ADVICE_SETTINGS["price_weight"]

        # Basic safety: force non-negative
        s = max(0.0, float(s))
        p = max(0.0, float(p))

        total = s + p
        if total == 0:
            # Both zero would break scoring — fall back to equal weights
            s, p = 0.5, 0.5
        else:
            # Normalize so they always sum to 1.0
            s = s / total
            p = p / total

        _ADVICE_SETTINGS["sentiment_weight"] = round(s, 4)
        _ADVICE_SETTINGS["price_weight"] = round(p, 4)

    # --- Update thresholds if provided ---
    if buy_threshold is not None:
        _ADVICE_SETTINGS["buy_threshold"] = float(buy_threshold)

    if sell_threshold is not None:
        _ADVICE_SETTINGS["sell_threshold"] = float(sell_threshold)

    return get_advice_settings()


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float safely. Returns default on any failure."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    """Keep a number inside [low, high]."""
    return max(low, min(high, value))


def _compute_price_momentum(
    price_history: list[float] | None,
    price_weight: float,
) -> tuple[float, str | None]:
    """
    Calculate simple momentum from a list of closing prices (oldest → newest).

    Returns
    -------
    (momentum_score, reason_or_None)
        momentum_score is already scaled by price_weight
        reason is a human-readable string if calculation succeeded, else None
    """
    if not price_history or not isinstance(price_history, list) or len(price_history) < 2:
        return 0.0, None

    # Keep only valid numbers
    closes = [_safe_float(p) for p in price_history if _safe_float(p) > 0]
    if len(closes) < 2:
        return 0.0, None

    first = closes[0]
    last = closes[-1]

    # Raw percentage change, then clip so extreme moves don't dominate
    raw_change = (last - first) / first
    clipped = _clamp(raw_change, -1.0, 1.0)

    # Scale by the current price weight
    contribution = clipped * price_weight

    # Build a short reason
    pct = raw_change * 100
    direction = "up" if raw_change > 0 else "down" if raw_change < 0 else "flat"
    reason = f"Price moved {direction} {abs(pct):.1f}% over the available history"

    return contribution, reason


def _decide_action(
    score: float,
    has_data: bool,
    already_held: bool,
    buy_threshold: float,
    sell_threshold: float,
) -> str:
    """
    Map the numeric score to a human action.
    Special cases for low data and existing holdings.
    """
    if not has_data:
        return "Watch"

    if score > buy_threshold:
        # If we already own it, prefer Hold instead of shouting "Buy more"
        if already_held:
            return "Hold"
        return "Buy"

    if score < sell_threshold:
        return "Sell"

    return "Hold"


def _decide_confidence(
    score: float,
    article_count: int,
    has_price_data: bool,
) -> str:
    """
    Simple, transparent confidence rules.
    """
    strength = abs(score)
    has_good_sentiment = article_count >= 3
    has_both_signals = has_good_sentiment and has_price_data

    if has_both_signals and strength >= 0.40:
        return "High"
    if (has_good_sentiment or has_price_data) and strength >= 0.15:
        return "Medium"
    return "Low"


def generate_advice(
    ticker: str,
    sentiment: dict | None = None,
    current_price: float | None = None,
    price_history: list[float] | None = None,
    holdings: dict | None = None,
) -> dict[str, Any]:
    """
    Produce a simple trading suggestion from sentiment and optional price data.

    Uses the current values from get_advice_settings().
    Call update_advice_settings() beforehand if you want different weights.

    Parameters
    ----------
    ticker : str
        Stock symbol (used only for the summary and reasons).
    sentiment : dict or None
        Result from logic.sentiment.analyze_news().
        Expected keys: "score", "label", "article_count".
    current_price : float or None
        Latest price (optional — currently used only in the summary).
    price_history : list[float] or None
        Recent closing prices, oldest → newest.
        Needs at least 2 valid points to contribute to the score.
    holdings : dict or None
        Current portfolio, e.g. {"AAPL": 10, "MSFT": 5}.
        If the ticker is already owned, strong Buy signals become "Hold".

    Returns
    -------
    dict
        {
            "action": "Buy" | "Hold" | "Sell" | "Watch",
            "confidence": "Low" | "Medium" | "High",
            "score": float,          # roughly -1.0 … +1.0
            "reasons": list[str],
            "summary": str
        }
    """
    # ------------------------------------------------------------------
    # 0. Read the live settings (so changes via update_advice_settings apply)
    # ------------------------------------------------------------------
    settings = get_advice_settings()
    sentiment_weight = settings["sentiment_weight"]
    price_weight = settings["price_weight"]
    buy_threshold = settings["buy_threshold"]
    sell_threshold = settings["sell_threshold"]

    # ------------------------------------------------------------------
    # 1. Normalize inputs so nothing downstream can crash
    # ------------------------------------------------------------------
    ticker = (ticker or "").strip().upper() or "UNKNOWN"

    # Sentiment defaults
    if not isinstance(sentiment, dict):
        sentiment = {}
    sent_score = _safe_float(sentiment.get("score"), 0.0)
    sent_label = str(sentiment.get("label") or "Neutral")
    article_count = int(sentiment.get("article_count") or 0)

    # Holdings
    already_held = False
    if isinstance(holdings, dict):
        shares = _safe_float(holdings.get(ticker), 0.0)
        already_held = shares > 0

    # ------------------------------------------------------------------
    # 2. Calculate the two signal contributions
    # ------------------------------------------------------------------
    reasons: list[str] = []

    # --- Sentiment contribution ---
    sentiment_contribution = sent_score * sentiment_weight
    if article_count > 0:
        reasons.append(
            f"News sentiment is {sent_label.lower()} "
            f"(score {sent_score:+.2f} from {article_count} article{'s' if article_count != 1 else ''})"
        )
    else:
        reasons.append("No usable news sentiment available")

    # --- Price momentum contribution ---
    price_contribution, price_reason = _compute_price_momentum(price_history, price_weight)
    has_price_data = price_reason is not None
    if price_reason:
        reasons.append(price_reason)
    else:
        reasons.append("No usable price history for momentum")

    # Optional: mention current price if it was provided
    price_val = _safe_float(current_price)
    if price_val > 0:
        reasons.append(f"Current price: ${price_val:.2f}")

    # ------------------------------------------------------------------
    # 3. Combine into a final score
    # ------------------------------------------------------------------
    raw_score = sentiment_contribution + price_contribution
    final_score = round(_clamp(raw_score), 4)

    # Do we have any real signal at all?
    has_data = (article_count > 0) or has_price_data

    # ------------------------------------------------------------------
    # 4. Decide action and confidence
    # ------------------------------------------------------------------
    action = _decide_action(
        final_score, has_data, already_held, buy_threshold, sell_threshold
    )
    confidence = _decide_confidence(final_score, article_count, has_price_data)

    # Extra reason when holdings changed the recommendation
    if already_held and action == "Hold" and final_score > buy_threshold:
        reasons.append("Already holding shares → preferring Hold over Buy")

    # ------------------------------------------------------------------
    # 5. Build a short natural-language summary
    # ------------------------------------------------------------------
    if not has_data:
        summary = f"Not enough data to form an opinion on {ticker}. Consider watching for now."
    else:
        direction = "bullish" if final_score > 0.05 else "bearish" if final_score < -0.05 else "neutral"
        strength = "strongly" if abs(final_score) >= 0.4 else "mildly" if abs(final_score) >= 0.15 else "slightly"
        summary = (
            f"{strength.capitalize()} {direction} on {ticker} "
            f"(score {final_score:+.2f}). Suggested action: {action}."
        )

    return {
        "action": action,
        "confidence": confidence,
        "score": final_score,
        "reasons": reasons,
        "summary": summary,
    }


# ------------------------------------------------------------------
# Quick manual test (run this file directly)
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Testing generate_advice() + settings system")
    print("=" * 60)

    print("\nCurrent settings:")
    for k, v in get_advice_settings().items():
        print(f"  {k}: {v}")

    # --- Scenario 1: Strong bullish case ---
    print("\n1. Strong bullish case (default weights)")
    result = generate_advice(
        ticker="AAPL",
        sentiment={"score": 0.65, "label": "Positive", "article_count": 5},
        current_price=195.40,
        price_history=[180.0, 185.0, 190.0, 194.0, 195.40],
        holdings={},
    )
    print(f"   Action     : {result['action']}")
    print(f"   Confidence : {result['confidence']}")
    print(f"   Score      : {result['score']:+.4f}")
    print(f"   Summary    : {result['summary']}")

    # --- Scenario 2: Change weights on the fly ---
    print("\n2. Same data but with heavier sentiment weight (0.8 / 0.2)")
    update_advice_settings(sentiment_weight=0.8, price_weight=0.2)
    print("   New settings:", get_advice_settings())
    result = generate_advice(
        ticker="AAPL",
        sentiment={"score": 0.65, "label": "Positive", "article_count": 5},
        current_price=195.40,
        price_history=[180.0, 185.0, 190.0, 194.0, 195.40],
        holdings={},
    )
    print(f"   Action     : {result['action']}")
    print(f"   Score      : {result['score']:+.4f}")

    # --- Reset to defaults for the remaining tests ---
    update_advice_settings(sentiment_weight=0.6, price_weight=0.4)

    # --- Scenario 3: Almost no data ---
    print("\n3. Almost no data (should become Watch)")
    result = generate_advice(ticker="XYZ")
    print(f"   Action     : {result['action']}")
    print(f"   Confidence : {result['confidence']}")
    print(f"   Summary    : {result['summary']}")

    # --- Scenario 4: Mild positive + already holding ---
    print("\n4. Mild positive while already holding")
    result = generate_advice(
        ticker="MSFT",
        sentiment={"score": 0.35, "label": "Positive", "article_count": 3},
        current_price=420.0,
        price_history=[400.0, 405.0, 410.0, 415.0, 420.0],
        holdings={"MSFT": 8},
    )
    print(f"   Action     : {result['action']}")
    print(f"   Score      : {result['score']:+.4f}")
    print(f"   Summary    : {result['summary']}")
