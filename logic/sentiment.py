"""
logic/sentiment.py
------------------
Sentiment analysis for news articles using NLTK VADER.
"""

from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Create the analyzer once when the module is imported.
# VADER is lightweight, so keeping a single instance is fine.
_sia = SentimentIntensityAnalyzer()


def score_text(text: str) -> float:
    """
    Return the VADER compound sentiment score for a piece of text.

    Parameters
    ----------
    text : str
        Any text (title, summary, or combination).

    Returns
    -------
    float
        Compound score in the range [-1.0, +1.0].
        0.0 is returned for empty / invalid input.
    """
    if not text or not isinstance(text, str):
        return 0.0

    scores = _sia.polarity_scores(text)
    return scores["compound"]


def _label_from_score(score: float) -> str:
    """Convert a compound score into a simple Positive / Neutral / Negative label."""
    if score > 0.05:
        return "Positive"
    if score < -0.05:
        return "Negative"
    return "Neutral"


def analyze_news(news_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Analyze a list of news articles and return an overall sentiment summary
    plus the individual score for every article.

    Parameters
    ----------
    news_list : list[dict]
        List of article dicts (as returned by data.news.get_news).
        Each dict should have at least a "title" key; "summary" is optional.

    Returns
    -------
    dict
        {
            "score": float,          # average compound score (rounded to 4 decimals)
            "label": str,            # "Positive", "Neutral", or "Negative"
            "article_count": int,    # how many articles contributed to the score
            "articles": [            # one entry per article
                {
                    "title": str,
                    "score": float,
                    "label": str
                },
                ...
            ]
        }
    """
    # Graceful handling when the list is empty or invalid
    if not news_list or not isinstance(news_list, list):
        return {
            "score": 0.0,
            "label": "Neutral",
            "article_count": 0,
            "articles": [],
        }

    article_details: list[dict[str, Any]] = []
    scores: list[float] = []

    for article in news_list:
        if not isinstance(article, dict):
            continue

        # Combine title + summary for a richer signal
        title = article.get("title", "") or ""
        summary = article.get("summary", "") or ""
        text = f"{title}. {summary}".strip()

        if not text:
            continue

        compound = score_text(text)
        scores.append(compound)

        article_details.append({
            "title": title,
            "score": round(compound, 4),
            "label": _label_from_score(compound),
        })

    # Safety: if no usable text was found
    if not scores:
        return {
            "score": 0.0,
            "label": "Neutral",
            "article_count": 0,
            "articles": [],
        }

    # Average the compound scores
    avg_score = sum(scores) / len(scores)

    return {
        "score": round(avg_score, 4),
        "label": _label_from_score(avg_score),
        "article_count": len(scores),
        "articles": article_details,
    }
