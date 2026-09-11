import re
import logging
import httpx
import feedparser
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from digests.models import Source
from .base import BaseIngestor, RawArticle
from .rss import clean_html_text

logger = logging.getLogger(__name__)


class TwitterIngestor(BaseIngestor):
    """
    Ingestor pour Twitter / X permettant de suivre un compte utilisateur ou hashtag.
    Supporte les URLs directes RSSHub/Nitter ainsi que les profils x.com ou twitter.com/@utilisateur.
    """

    HANDLE_REGEX = re.compile(r"(?:twitter\.com|x\.com)/@?([a-zA-Z0-9_]{1,50})")

    def _extract_handle(self, url: str) -> str:
        url = url.strip()
        if url.startswith("@"):
            return url[1:]
        match = self.HANDLE_REGEX.search(url)
        if match:
            return match.group(1)
        # Si c'est juste un pseudo brut
        if "/" not in url and not url.startswith("http"):
            return url
        return ""

    def fetch(self, source: Source) -> list[RawArticle]:
        url = source.url.strip()
        articles = []

        # Si l'URL est déjà un flux RSS/Atom (ex: RSSHub ou Nitter)
        if "rss" in url.lower() or "atom" in url.lower() or "feed" in url.lower():
            return self._fetch_via_feed(source, url)

        handle = self._extract_handle(url)
        if not handle:
            # Tenter quand même en flux RSS direct
            return self._fetch_via_feed(source, url)

        # Tentative 1 : Endpoint de syndication public de Twitter/X (sans clé API)
        try:
            syndication_url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                res = client.get(syndication_url, headers=headers)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    # Les tweets sont encodés dans des balises data ou blocs de timeline
                    tweet_blocks = soup.find_all("article") or soup.find_all("div", attrs={"data-tweet-id": True})

                    for block in tweet_blocks[:15]:
                        text_elem = block.find("div", lang=True) or block.find("p")
                        if not text_elem:
                            continue
                        tweet_text = text_elem.get_text(separator=" ", strip=True)
                        if not tweet_text:
                            continue

                        # Trouver le lien vers le tweet
                        link_elem = block.find("a", href=re.compile(r"/status/\d+"))
                        tweet_url = f"https://x.com{link_elem['href']}" if link_elem else f"https://x.com/{handle}"

                        title = f"Post de @{handle} : {tweet_text[:60]}..."
                        content = f"[Twitter/X @{handle}]\n\n{tweet_text}"

                        articles.append(
                            RawArticle(
                                title=title,
                                url=tweet_url,
                                raw_content=content,
                                published_at=datetime.now(timezone.utc),
                                source=source,
                            )
                        )

                    if articles:
                        return articles
        except Exception as e:
            logger.warning(f"Échec de l'ingestion Twitter syndication pour {handle}: {e}. Tentative via passerelle RSS...")

        # Tentative 2 : Passerelle RSSHub publique
        rsshub_url = f"https://rsshub.app/twitter/user/{handle}"
        return self._fetch_via_feed(source, rsshub_url, handle=handle)

    def _fetch_via_feed(self, source: Source, feed_url: str, handle: str = "") -> list[RawArticle]:
        feed = feedparser.parse(feed_url)
        articles = []

        for entry in feed.entries:
            tweet_url = entry.get("link")
            if not tweet_url:
                continue

            raw_text = entry.get("summary", "") or entry.get("description", "")
            clean_text = clean_html_text(raw_text)
            author = handle or source.name
            title = entry.get("title") or f"Post de @{author} : {clean_text[:60]}"

            published = entry.get("published_parsed")
            published_at = (
                datetime(*published[:6], tzinfo=timezone.utc)
                if published
                else datetime.now(timezone.utc)
            )

            articles.append(
                RawArticle(
                    title=title.strip(),
                    url=tweet_url,
                    raw_content=f"[Twitter/X @{author}]\n\n{clean_text}",
                    published_at=published_at,
                    source=source,
                )
            )

        return articles
