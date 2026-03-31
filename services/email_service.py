"""שירות בנייה ושליחה של מייל העיתון."""

import smtplib
from email.mime.text import MIMEText
from typing import Dict, List


def html_escape(text: str) -> str:
    """מונע שבירת HTML ע"י תווים מיוחדים."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_email_html(newspaper_data: Dict, selected_articles: List[Dict]) -> str:
    """בונה HTML מסודר למייל מהנתונים שנוצרו."""
    title = html_escape(newspaper_data.get("title", "העיתון השבועי שלך"))
    intro = html_escape(newspaper_data.get("intro", ""))

    articles_html = []
    for i, article in enumerate(newspaper_data.get("articles", [])):
        source_article = selected_articles[i] if i < len(selected_articles) else {}
        article_title = html_escape(article.get("title", ""))
        summary = html_escape(article.get("summary", ""))
        details = html_escape(article.get("details", ""))
        personal_note = html_escape(article.get("personal_note", ""))
        source = html_escape(source_article.get("source", ""))
        article_url = html_escape(source_article.get("url", ""))

        source_block = f"<p><strong>מקור:</strong> {source}</p>" if source else ""
        read_more = (
            f'<p><a href="{article_url}" target="_blank">לכתבה המקורית</a></p>'
            if article_url
            else ""
        )

        articles_html.append(
            f"""
            <div style="margin-bottom: 24px; border-bottom: 1px solid #ddd; padding-bottom: 12px;">
                <h2>{article_title}</h2>
                <p><strong>{summary}</strong></p>
                <p>{details}</p>
                {source_block}
                <p><em>{personal_note}</em></p>
                {read_more}
            </div>
            """
        )

    railway_url = "https://web-production-85103.up.railway.app"

    view_button = f"""
    <div style="text-align:center;margin:32px 0;">
      <a href="{railway_url}" target="_blank"
         style="display:inline-block;background-color:#1e3a5f;color:#ffffff;
                font-size:20px;font-weight:bold;text-decoration:none;
                padding:18px 40px;border-radius:50px;
                font-family:Arial,Helvetica,sans-serif;letter-spacing:0.5px;
                box-shadow:0 4px 12px rgba(30,58,95,0.35);">
        📰 לצפייה בעיתון המלא
      </a>
    </div>
    """

    return f"""
    <html dir="rtl" lang="he">
      <head><meta charset="utf-8"></head>
      <body style="font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:0 auto;">
        <h1>{title}</h1>
        <p>{intro}</p>
        {view_button}
        {''.join(articles_html)}
        {view_button}
      </body>
    </html>
    """


def send_email(
    to_email: str,
    sender_email: str,
    app_password: str,
    html_content: str,
) -> bool:
    """שולח מייל ומחזיר הצלחה/כישלון."""
    msg = MIMEText(html_content, "html")
    msg["Subject"] = "📰 העיתון השבועי שלך"
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        return True
    except smtplib.SMTPAuthenticationError as exc:
        print(
            "\n[ERROR] Gmail authentication failed. "
            "Verify SENDER_EMAIL/SENDER_APP_PASSWORD in .env, make sure 2-Step Verification is enabled, "
            "and use a Google App Password (not your regular account password)."
        )
        print(f"[DETAILS] {exc}")
        return False
    except Exception as exc:
        print(f"\n[ERROR] Failed sending email: {exc}")
        return False
