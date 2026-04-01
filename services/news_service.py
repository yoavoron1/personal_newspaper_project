"""שירות לשליפה וסינון כתבות חדשות."""

from datetime import datetime, timedelta
from typing import Dict, List
from urllib.parse import urlparse

import requests


TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Readable display names for well-known domains
_DOMAIN_NAMES: Dict[str, str] = {
    "techcrunch.com": "TechCrunch", "theverge.com": "The Verge",
    "wired.com": "Wired", "arstechnica.com": "Ars Technica",
    "engadget.com": "Engadget", "gizmodo.com": "Gizmodo",
    "reuters.com": "Reuters", "apnews.com": "AP News",
    "cnn.com": "CNN", "bbc.com": "BBC", "bbc.co.uk": "BBC",
    "theguardian.com": "The Guardian", "nytimes.com": "NY Times",
    "wsj.com": "Wall Street Journal", "bloomberg.com": "Bloomberg",
    "ft.com": "Financial Times", "economist.com": "The Economist",
    "washingtonpost.com": "Washington Post", "theatlantic.com": "The Atlantic",
    "axios.com": "Axios", "politico.com": "Politico",
    "time.com": "Time", "forbes.com": "Forbes",
    "businessinsider.com": "Business Insider", "slate.com": "Slate",
    "nature.com": "Nature", "science.org": "Science",
    "scientificamerican.com": "Scientific American",
    "newscientist.com": "New Scientist", "phys.org": "Phys.org",
    "livescience.com": "Live Science", "futurism.com": "Futurism",
    "healthline.com": "Healthline", "medicalnewstoday.com": "Medical News Today",
    "nih.gov": "NIH", "nasa.gov": "NASA", "who.int": "WHO",
    "space.com": "Space.com", "nationalgeographic.com": "Nat Geo",
    "mit.edu": "MIT", "stanford.edu": "Stanford", "harvard.edu": "Harvard",
    "haaretz.com": "Haaretz", "timesofisrael.com": "Times of Israel",
    "jpost.com": "Jerusalem Post", "ynetnews.com": "Ynet",
    "vogue.com": "Vogue", "elle.com": "Elle",
    "independent.co.uk": "The Independent", "thetimes.co.uk": "The Times",
    "vice.com": "Vice",
}

_DOMAIN_COUNTRIES: Dict[str, str] = {
    "bbc.com": "UK", "bbc.co.uk": "UK", "theguardian.com": "UK",
    "ft.com": "UK", "economist.com": "UK", "newscientist.com": "UK",
    "thetimes.co.uk": "UK", "independent.co.uk": "UK",
    "reuters.com": "International", "apnews.com": "USA",
    "cnn.com": "USA", "nytimes.com": "USA", "wsj.com": "USA",
    "bloomberg.com": "USA", "washingtonpost.com": "USA",
    "haaretz.com": "Israel", "timesofisrael.com": "Israel",
    "jpost.com": "Israel", "ynetnews.com": "Israel",
}

_TLD_COUNTRIES: Dict[str, str] = {
    ".co.uk": "UK", ".uk": "UK", ".de": "Germany", ".fr": "France",
    ".it": "Italy", ".es": "Spain", ".au": "Australia", ".ca": "Canada",
    ".il": "Israel", ".jp": "Japan", ".cn": "China", ".in": "India",
    ".br": "Brazil",
}


def _source_name_from_url(url: str) -> str:
    """מחלץ שם מקור קריא מ-URL."""
    try:
        netloc = urlparse(url).netloc.lower()
        domain = netloc[4:] if netloc.startswith("www.") else netloc
        if domain in _DOMAIN_NAMES:
            return _DOMAIN_NAMES[domain]
        root = domain.split(".")[0]
        return root.replace("-", " ").title() if root else domain
    except Exception:
        return ""


def _country_from_url(url: str) -> str:
    """מנסה להסיק מדינת מקור מה-URL."""
    try:
        netloc = urlparse(url).netloc.lower()
        domain = netloc[4:] if netloc.startswith("www.") else netloc
        if domain in _DOMAIN_COUNTRIES:
            return _DOMAIN_COUNTRIES[domain]
        for tld, country in _TLD_COUNTRIES.items():
            if domain.endswith(tld):
                return country
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return "USA"
        return "USA"
    except Exception:
        return ""


def fetch_articles_with_tavily(
    topics: List[str],
    tavily_api_key: str,
    max_results_per_topic: int = 5,
) -> List[Dict]:
    """מביא כתבות עדכניות מ-Tavily Advanced Search לכל נושא (ישירות ב-REST)."""
    all_results: List[Dict] = []

    for topic in topics:
        try:
            payload = {
                "api_key": tavily_api_key,
                "query": topic,
                "search_depth": "advanced",
                "max_results": max_results_per_topic,
                "include_answer": False,
                "include_raw_content": False,
                "include_images": True,
            }
            response = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            images = data.get("images", [])
            for idx, r in enumerate(results):
                url = (r.get("url") or "").strip()
                img = (r.get("image") or "").strip()
                if not img and idx < len(images):
                    img = (images[idx] or "").strip()
                all_results.append({
                    "topic": topic,
                    "title": (r.get("title") or "").strip(),
                    "content": (r.get("content") or "").strip(),
                    "url": url,
                    "score": r.get("score", 0),
                    "image": img,
                    "source_name": _source_name_from_url(url),
                    "country_origin": _country_from_url(url),
                })
            print(f"  Tavily [{topic}] → {len(results)} results")
        except Exception as exc:
            print(f"\n[ERROR] Tavily search failed for '{topic}': {exc}")

    return all_results


def fetch_articles_for_keyword(
    keyword: str,
    news_key: str,
    days_back: int = 7,
    max_articles: int = 3,
) -> List[Dict]:
    """מביא כתבות עבור מילת מפתח אחת מהימים האחרונים."""
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = "https://newsapi.org/v2/everything"
    attempt_params = [
        {
            "q": keyword,
            "from": from_date,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": max_articles,
            "apiKey": news_key,
        },
        {
            "q": keyword,
            "from": from_date,
            "sortBy": "publishedAt",
            "pageSize": max_articles,
            "apiKey": news_key,
        },
    ]

    data = None
    for params in attempt_params:
        try:
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()
            candidate = response.json()
        except Exception as exc:
            print(f"\n[ERROR] News request failed for keyword '{keyword}': {exc}")
            continue

        if candidate.get("status") == "ok" and candidate.get("articles"):
            data = candidate
            break
        if candidate.get("status") == "ok" and data is None:
            data = candidate

    if not data:
        return []
    if data.get("status") != "ok":
        print(f"\n[ERROR] News API returned an error for '{keyword}': {data}")
        return []

    results: List[Dict] = []
    for article in data.get("articles", []):
        title = (article.get("title") or "").strip()
        description = (article.get("description") or "").strip()
        article_url = (article.get("url") or "").strip()
        source = ((article.get("source") or {}).get("name") or "").strip()
        published_at = (article.get("publishedAt") or "").strip()
        image_url = (article.get("urlToImage") or "").strip()

        if not title or title == "[Removed]" or not article_url:
            continue

        results.append(
            {
                "keyword": keyword,
                "title": title,
                "description": description,
                "url": article_url,
                "source": source,
                "published_at": published_at,
                "image": image_url,
            }
        )

    return results


def deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """מסיר כפילויות לפי קישור ו/או כותרת."""
    seen_urls = set()
    seen_titles = set()
    unique_articles = []

    for article in articles:
        article_url = article.get("url", "").strip().lower()
        title = article.get("title", "").strip().lower()
        if not article_url or article_url in seen_urls or title in seen_titles:
            continue

        seen_urls.add(article_url)
        seen_titles.add(title)
        unique_articles.append(article)

    return unique_articles
