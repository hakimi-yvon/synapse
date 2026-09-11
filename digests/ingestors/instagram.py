import re
import logging
import feedparser
from datetime import datetime, timezone
from digests.models import Source
from .base import BaseIngestor, RawArticle
from .rss import clean_html_text

logger = logging.getLogger(__name__)


class InstagramIngestor(BaseIngestor):
    """
    Ingestor pour profils Instagram via passerelles publiques RSS (RSSHub, Picuki).
    Permet de récupérer les dernières publications, légendes et visuels d'un compte public.
    """

    HANDLE_REGEX = re.compile(r"instagram\.com/([a-zA-Z0-9_\.]+)")

    def _extract_handle(self, url: str) -> str:
        url = url.strip()
        if url.startswith("@"):
            return url[1:]
        match = self.HANDLE_REGEX.search(url)
        if match:
            return match.group(1)
        if "/" not in url and not url.startswith("http"):
            return url
        return ""

    def fetch(self, source: Source) -> list[RawArticle]:
        url = source.url.strip()

        # Si l'URL est déjà un flux RSS direct
        if "rss" in url.lower() or "atom" in url.lower() or "feed" in url.lower():
            return self._fetch_via_feed(source, url)

        handle = self._extract_handle(url)
        if not handle:
            return self._fetch_via_feed(source, url)

        # Utilisation de la passerelle RSSHub standard pour Instagram
        feed_url = f"https://rsshub.app/instagram/user/{handle}"
        return self._fetch_via_feed(source, feed_url, handle=handle)

    def _fetch_via_feed(self, source: Source, feed_url: str, handle: str = "") -> list[RawArticle]:
        feed = feedparser.parse(feed_url)
        articles = []

        for entry in feed.entries:
            post_url = entry.get("link")
            if not post_url:
                continue

            caption_html = entry.get("summary", "") or entry.get("description", "")
            clean_caption = clean_html_text(caption_html)
            author = handle or source.name

            title = entry.get("title") or f"Publication Instagram de @{author} : {clean_caption[:50]}..."

            published = entry.get("published_parsed")
            published_at = (
                datetime(*published[:6], tzinfo=timezone.utc)
                if published
                else datetime.now(timezone.utc)
            )

            articles.append(
                RawArticle(
                    title=title.strip(),
                    url=post_url,
                    raw_content=f"[Instagram @{author}]\n\n{clean_caption}",
                    published_at=published_at,
                    source=source,
                )
            )

        return articles
