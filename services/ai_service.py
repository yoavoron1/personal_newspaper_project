"""שירות AI להפקת מילות מפתח, סינון וכתיבת עיתון אישי."""

import json
from typing import Dict, List, Optional

from openai import OpenAI

from utils.json_utils import safe_json_loads


class AIService:
    """מעטפת ליכולות OpenAI בפרויקט."""

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def extract_keywords(self, user_text_input: str) -> List[str]:
        """מחלץ מילות מפתח איכותיות באנגלית מתוך תיאור המשתמש."""
        prompt = f"""
        You extract news search keywords from user interests.
        Return ONLY valid JSON in this format:
        {{"keywords": ["keyword 1", "keyword 2"]}}
        Rules:
        - Keywords MUST be in English only.
        - Return 6-12 keywords.
        - Each keyword should be 1-4 words.
        - Prefer specific topics, avoid generic terms.

        קלט המשתמש:
        {user_text_input}
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
        except Exception as exc:
            print(f"\n[ERROR] Failed to extract keywords: {exc}")
            return []

        data = safe_json_loads(content)
        if not data or "keywords" not in data:
            return []

        cleaned = []
        for keyword in data["keywords"]:
            if isinstance(keyword, str):
                keyword = keyword.strip()
                if keyword and keyword.lower() not in {k.lower() for k in cleaned}:
                    cleaned.append(keyword)
        return self.ensure_english_keywords(cleaned)

    def ensure_english_keywords(self, keywords: List[str]) -> List[str]:
        """מוודא שמילות המפתח באנגלית; מתרגם אוטומטית כשצריך."""
        if not keywords:
            return []
        if all(self._is_mostly_english(keyword) for keyword in keywords):
            return keywords

        prompt = f"""
        Translate the following search keywords to natural English keywords for News API.
        Keep each keyword concise (1-4 words), preserve topic meaning, and return ONLY JSON:
        {{
          "keywords": ["...", "..."]
        }}

        keywords:
        {keywords}
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = safe_json_loads(response.choices[0].message.content)
            if data and "keywords" in data:
                translated = []
                for keyword in data["keywords"]:
                    if isinstance(keyword, str):
                        keyword = keyword.strip()
                        if keyword and keyword.lower() not in {k.lower() for k in translated}:
                            translated.append(keyword)
                if translated:
                    return translated
        except Exception as exc:
            print(f"\n[WARN] Could not translate keywords to English: {exc}")

        return keywords

    @staticmethod
    def _is_mostly_english(text: str) -> bool:
        """בודק אם מחרוזת בנויה בעיקר מאותיות לטיניות."""
        latin_chars = 0
        letter_chars = 0
        for ch in text:
            if ch.isalpha():
                letter_chars += 1
                if "a" <= ch.lower() <= "z":
                    latin_chars += 1
        if letter_chars == 0:
            return True
        return (latin_chars / float(letter_chars)) >= 0.8

    def filter_trash_articles(self, articles: List[Dict]) -> List[Dict]:
        """מסנן כתבות טראש ומחזיר רק כתבות איכותיות."""
        if not articles:
            return []

        filtered: List[Dict] = []
        for article in articles:
            title = article.get("title", "").strip()
            description = article.get("description", "").strip()
            content = f"Title: {title}\nDescription: {description}"

            prompt = f"""
            בדוק אם הכתבה היא טראש.
            החזר JSON בלבד:
            {{
              "is_trash": true או false,
              "explanation": "הסבר קצר"
            }}

            כתבה:
            {content}
            """

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                data = safe_json_loads(response.choices[0].message.content)
            except Exception as exc:
                print(f"\n[ERROR] Failed to classify article '{title[:40]}...': {exc}")
                filtered.append(article)
                continue

            if data and "is_trash" in data and not data["is_trash"]:
                filtered.append(article)
            elif not data:
                filtered.append(article)

        return filtered

    def select_best_articles(
        self,
        user_text_input: str,
        family_info_input: str,
        articles: List[Dict],
        top_n: int = 4,
    ) -> List[Dict]:
        """מדורג ובוחר את הכתבות המתאימות ביותר למשתמש."""
        if not articles:
            return []

        article_lines = []
        for i, article in enumerate(articles, start=1):
            article_lines.append(
                f"{i}. Title: {article['title']}\n"
                f"Description: {article['description']}\n"
                f"Keyword: {article['keyword']}\n"
                f"Source: {article['source']}\n"
                f"URL: {article['url']}\n"
            )

        prompt = f"""
        User interests:
        {user_text_input}

        Family context:
        {family_info_input}

        Return JSON:
        {{
          "selected_indices": [1, 2, 3, 4]
        }}

        Articles:
        {chr(10).join(article_lines)}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            data = safe_json_loads(response.choices[0].message.content)
        except Exception as exc:
            print(f"\n[ERROR] Failed to rank articles: {exc}")
            return articles[:top_n]

        if not data or "selected_indices" not in data:
            return articles[:top_n]

        selected = []
        for idx in data["selected_indices"]:
            if isinstance(idx, int) and 1 <= idx <= len(articles):
                selected.append(articles[idx - 1])

        if len(selected) < top_n:
            selected_urls = {a["url"] for a in selected}
            for article in articles:
                if article["url"] not in selected_urls:
                    selected.append(article)
                    selected_urls.add(article["url"])
                if len(selected) >= top_n:
                    break

        return selected[:top_n]

    def write_newspaper(
        self,
        user_name: str,
        user_text_input: str,
        family_info_input: str,
        writing_style_input: str,
        selected_articles: List[Dict],
    ) -> Optional[Dict]:
        """כותב עיתון אישי בפורמט JSON."""
        if not selected_articles:
            return None

        article_block = []
        for i, article in enumerate(selected_articles, start=1):
            article_block.append(
                f"{i}. Title: {article['title']}\n"
                f"Description: {article['description']}\n"
            )

        prompt = f"""
        צור עיתון שבועי אישי בעברית.
        החזר JSON בפורמט:
        {{
          "title": "כותרת",
          "intro": "פתיחה",
          "articles": [
            {{
              "title": "כותרת כתבה",
              "summary": "תקציר",
              "details": "פירוט",
              "personal_note": "הערה אישית"
            }}
          ]
        }}

        שם המשתמש: {user_name}
        תחומי עניין: {user_text_input}
        משפחה: {family_info_input}
        סגנון כתיבה: {writing_style_input}
        כתבות מקור:
        {chr(10).join(article_block)}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as exc:
            print(f"\n[ERROR] Failed to write newspaper: {exc}")
            return None
