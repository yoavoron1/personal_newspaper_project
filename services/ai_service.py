"""שירות AI להפקת מילות מפתח, סינון וכתיבת עיתון אישי."""

import json
from typing import Dict, List, Optional
from urllib.parse import quote

from openai import OpenAI

from utils.json_utils import safe_json_loads

UNSPLASH_FALLBACK = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&h=500&fit=crop&q=80"


def _unsplash_url(article: Dict) -> str:
    """בונה URL לתמונה מ-Unsplash לפי מילות המפתח שה-AI סיפק."""
    raw = (article.get("image_keywords") or "").strip()
    if not raw:
        # Fall back to topic if no keywords
        raw = (article.get("topic") or "news journalism").strip()
    words = [w.strip(".,;:") for w in raw.split() if w.strip()][:4]
    slug = quote(",".join(words), safe=",")
    return f"https://source.unsplash.com/featured/800x500/?{slug}"


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

    def write_newspaper_from_tavily(
        self,
        user_name: str,
        user_text_input: str,
        family_info_input: str,
        writing_style_input: str,
        tavily_results: List[Dict],
    ) -> Optional[Dict]:
        """כותב עיתון אישי מתוצאות Tavily בפורמט חדש עם bullet points ו'למה זה חשוב'."""
        if not tavily_results:
            return None

        context_lines = []
        for i, r in enumerate(tavily_results, start=1):
            context_lines.append(
                f"[{i}] TOPIC: {r['topic']}\n"
                f"    SOURCE: {r.get('source_name', '')} ({r.get('country_origin', '')})\n"
                f"    TITLE: {r['title']}\n"
                f"    CONTENT: {r['content'][:500]}\n"
                f"    URL: {r['url']}\n"
            )

        prompt = f"""
אתה עורך עיתון דיגיטלי אישי בעברית. קיבלת תוצאות חיפוש עדכניות מהאינטרנט.

תפקידך:
1. סנן clickbait, פרסומות וחדשות שוליות ללא ערך אמיתי
2. בחר 4-5 כתבות בעלות הערך הגבוה ביותר, שמותאמות לפרופיל המשתמש
3. כתוב שתי רמות תוכן בעברית לכל כתבה: תקציר קצר לדף הבית וניתוח מעמיק לדף הכתבה

החזר JSON בפורמט הבא בלבד:
{{
  "title": "כותרת העיתון (יצירתית, בעברית)",
  "intro": "פתיחה אישית קצרה ומחממת למשתמש (1-2 משפטים)",
  "articles": [
    {{
      "title": "כותרת הכתבה בעברית",
      "topic": "נושא הכתבה",
      "short_summary": "פסקה אחת של 2-3 משפטים. פסקה זו מסכמת מה הסיפור ומה הטייקאווי המרכזי שלו, ומעוררת סקרנות לקרוא עוד.",
      "why_it_matters": "למה זה חשוב — משפט אחד עד שניים, ממוקד ובעל ערך אמיתי.",
      "personal_note": "הערה אישית רלוונטית למשתמש הספציפי, תוך התחשבות בגיל, תחומי עניין ורקע.",
      "long_summary": "פסקה ראשונה — הקשר ורקע: הצב את האירוע בהקשרו הרחב. מה השתנה, מדוע זה חשוב עכשיו, ומהי המשמעות ההיסטורית, המדעית או התרבותית (3-4 משפטים).\\n\\nפסקה שנייה — פרטים ונתונים: פרט את הממצאים הטכניים, הנתונים הכמותיים, שמות הגופים המעורבים, ומה בדיוק הוכח, הוכרז או התרחש (3-4 משפטים). היה מדויק ועמוק — הקורא אינו מסתפק בשטחיות.\\n\\nפסקה שלישית — השלכות ועתיד: לאן זה מוביל, מה עשוי להשתנות, ומה הזווית הביקורתית שמי שמעמיק בתחום זה חייב להכיר (3-4 משפטים). אל תחזור על תוכן short_summary או why_it_matters.",
      "personal_impact": "השפעה אישית: נתח כיצד חדשות זו קשורה ספציפית ל{user_name} — {family_info_input.strip()}. כתוב 2-3 משפטים בעברית מעמיקה ואקדמית, המחברים את הנושא לתחומי העניין שלה (מוזיקה חדשה, הופעות, טיולים בארץ, ספרות, שוק ההון).",
      "image_keywords": "three descriptive English words capturing the visual essence of this story (e.g. 'music concert crowd' or 'hiking trail nature')",
      "source_id": 3
    }}
  ]
}}

חוקים:
- כתוב רק בעברית (למעט image_keywords שחייב להיות באנגלית)
- source_id הוא מספר התוצאה המקורית מהרשימה למטה (מספר שלם)
- short_summary: פסקה אחת קצרה (2-3 משפטים), לא רשימה, מעוררת סקרנות
- why_it_matters: קצר, חד, שונה מ-short_summary
- long_summary: בדיוק 3 פסקאות מופרדות ב-\\n\\n, לא חוזר על short_summary או why_it_matters
- image_keywords: בדיוק 3 מילים באנגלית, ספציפיות וויזואליות (לדוגמה: "tennis serve stadium" ולא "sports news")

שם המשתמש: {user_name}
תחומי עניין: {user_text_input}
רקע אישי: {family_info_input}
סגנון כתיבה: {writing_style_input}

תוצאות חיפוש:
{chr(10).join(context_lines)}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=8000,
            )
            newspaper_data = json.loads(response.choices[0].message.content)
        except Exception as exc:
            print(f"\n[ERROR] Failed to write newspaper from Tavily: {exc}")
            return None

        for article in newspaper_data.get("articles", []):
            source_id = article.get("source_id")
            if isinstance(source_id, int) and 1 <= source_id <= len(tavily_results):
                source = tavily_results[source_id - 1]
                article["url"] = source.get("url", "")
                article["source_name"] = source.get("source_name", "")
                article["country_origin"] = source.get("country_origin", "")
                # Prefer Tavily image; fall back to Unsplash keyword search
                tavily_img = source.get("image", "").strip()
                article["image"] = tavily_img if tavily_img else _unsplash_url(article)
            else:
                article.setdefault("url", "")
                article.setdefault("source_name", "")
                article.setdefault("country_origin", "")
                article["image"] = _unsplash_url(article)

        return newspaper_data

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
