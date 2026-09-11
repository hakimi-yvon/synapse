from .base import BaseIngestor
from .rss import RSSIngestor
from .reddit import RedditIngestor
from .youtube import YouTubeIngestor
from .twitter import TwitterIngestor
from .instagram import InstagramIngestor


def get_ingestor(source_type: str) -> BaseIngestor:
    """
    Retourne l'ingestor adapté selon le type de source configuré.
    """
    source_type = (source_type or "").lower().strip()
    if source_type in ["reddit", "r"]:
        return RedditIngestor()
    elif source_type in ["youtube", "yt"]:
        return YouTubeIngestor()
    elif source_type in ["twitter", "x"]:
        return TwitterIngestor()
    elif source_type in ["instagram", "ig"]:
        return InstagramIngestor()
    else:
        # Par défaut: RSS / Atom
        return RSSIngestor()

