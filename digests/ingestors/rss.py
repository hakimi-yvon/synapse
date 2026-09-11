import feedparser
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from digests.models import Source
from .base import BaseIngestor, RawArticle


def clean_html_text(raw_html: str) -> str:
    """Nettoie le balisage HTML pour n'extraire que le texte lisible."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    # Supprime les balises scripts, styles et images
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


class RSSIngestor(BaseIngestor):
    def fetch(self, source: Source) -> list[RawArticle]:
        feed = feedparser.parse(source.url)
        articles = []

        for entry in feed.entries:
            url = entry.get("link")
            if not url:
                continue

            title = entry.get("title", "Sans titre").strip()

            # Extraction du meilleur contenu texte (content > summary > description)
            content = ""
            if "content" in entry and entry["content"]:
                content = entry["content"][0].get("value", "")
            elif "summary" in entry:
                content = entry.get("summary", "")
            elif "description" in entry:
                content = entry.get("description", "")

            cleaned_content = clean_html_text(content)

            published = entry.get("published_parsed")
            published_at = (
                datetime(*published[:6], tzinfo=timezone.utc)
                if published
                else datetime.now(timezone.utc)
            )

            articles.append(
                RawArticle(
                    title=title,
                    url=url,
                    raw_content=cleaned_content,
                    published_at=published_at,
                    source=source,
                )
            )

        return articles
