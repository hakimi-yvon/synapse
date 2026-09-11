import logging
import httpx
import feedparser
from datetime import datetime, timezone
from digests.models import Source
from .base import BaseIngestor, RawArticle
from .rss import clean_html_text

logger = logging.getLogger(__name__)


class RedditIngestor(BaseIngestor):
    """
    Ingestor pour subreddits Reddit via API JSON publique (sans clé requise)
    avec repli automatique sur le flux RSS natif de Reddit (.rss).
    """

    def fetch(self, source: Source) -> list[RawArticle]:
        url = source.url.strip().rstrip("/")

        # Normalisation de l'URL vers l'endpoint JSON
        if url.endswith(".rss"):
            json_url = url[:-4] + ".json?limit=25"
            rss_url = url
        elif url.endswith(".json"):
            json_url = url
            rss_url = url[:-5] + ".rss"
        else:
            json_url = f"{url}/top.json?t=day&limit=25"
            rss_url = f"{url}/top/.rss?t=day"

        articles = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SynapseBot/1.0"
        }

        # Tentative 1 : Endpoint JSON
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(json_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    children = data.get("data", {}).get("children", [])
                    for child in children:
                        post = child.get("data", {})
                        permalink = post.get("permalink")
                        if not permalink:
                            continue

                        post_url = f"https://www.reddit.com{permalink}"
                        title = post.get("title", "Sans titre").strip()
                        selftext = post.get("selftext", "").strip()
                        score = post.get("score", 0)
                        comments = post.get("num_comments", 0)
                        subreddit = post.get("subreddit", "")

                        context = f"[Reddit r/{subreddit} | {score} upvotes, {comments} commentaires]"
                        content = f"{context}\n\n{selftext}" if selftext else context

                        created_utc = post.get("created_utc")
                        published_at = (
                            datetime.fromtimestamp(created_utc, tz=timezone.utc)
                            if created_utc
                            else datetime.now(timezone.utc)
                        )

                        articles.append(
                            RawArticle(
                                title=title,
                                url=post_url,
                                raw_content=content,
                                published_at=published_at,
                                source=source,
                            )
                        )
                    return articles
        except Exception as e:
            logger.warning(f"Échec de l'ingestion Reddit JSON pour {source.name}: {e}. Tentative via RSS...")

        # Tentative 2 : Fallback sur le flux RSS de Reddit
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            post_url = entry.get("link")
            if not post_url:
                continue

            title = entry.get("title", "Sans titre").strip()
            raw_html = entry.get("content", [{}])[0].get("value", "") if "content" in entry else entry.get("summary", "")
            content = clean_html_text(raw_html)

            published = entry.get("published_parsed")
            published_at = (
                datetime(*published[:6], tzinfo=timezone.utc)
                if published
                else datetime.now(timezone.utc)
            )

            articles.append(
                RawArticle(
                    title=title,
                    url=post_url,
                    raw_content=f"[Reddit] {content}",
                    published_at=published_at,
                    source=source,
                )
            )

        return articles
