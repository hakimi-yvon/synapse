import re
import logging
import httpx
import feedparser
from datetime import datetime, timezone
from digests.models import Source
from .base import BaseIngestor, RawArticle

logger = logging.getLogger(__name__)


class YouTubeIngestor(BaseIngestor):
    """
    Ingestor pour chaînes YouTube via flux Atom/RSS natif de YouTube.
    Supporte les URLs directes de flux Atom (feeds/videos.xml) ainsi que les URLs de chaîne (@nom ou /channel/ID).
    """

    CHANNEL_ID_REGEX = re.compile(r'itemprop="channelId"\s+content="(UC[\w-]+)"')

    def _resolve_feed_url(self, url: str) -> str:
        url = url.strip()
        if "feeds/videos.xml" in url:
            return url

        # Si l'URL contient déjà /channel/UC...
        channel_match = re.search(r"youtube\.com/channel/(UC[\w-]+)", url)
        if channel_match:
            channel_id = channel_match.group(1)
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        # Sinon, tenter de résoudre le channelId depuis la page de la chaîne (@Handle)
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    match = self.CHANNEL_ID_REGEX.search(res.text)
                    if match:
                        channel_id = match.group(1)
                        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        except Exception as e:
            logger.warning(f"Impossible de résoudre automatiquement le channelId YouTube pour {url}: {e}")

        return url

    def fetch(self, source: Source) -> list[RawArticle]:
        feed_url = self._resolve_feed_url(source.url)
        feed = feedparser.parse(feed_url)
        articles = []

        for entry in feed.entries:
            video_url = entry.get("link")
            if not video_url:
                continue

            title = entry.get("title", "Sans titre").strip()

            # Extraction de la description vidéo YouTube
            description = ""
            if "media_description" in entry:
                description = entry.get("media_description", "")
            elif "summary" in entry:
                description = entry.get("summary", "")

            content = f"[Vidéo YouTube] {title}\n\n{description}"[:2000]

            published = entry.get("published_parsed")
            published_at = (
                datetime(*published[:6], tzinfo=timezone.utc)
                if published
                else datetime.now(timezone.utc)
            )

            articles.append(
                RawArticle(
                    title=title,
                    url=video_url,
                    raw_content=content,
                    published_at=published_at,
                    source=source,
                )
            )

        return articles
