from .base import BaseIngestor
from .rss import RSSIngestor
from .reddit import RedditIngestor
from .youtube import YouTubeIngestor


def get_ingestor(source_type: str) -> BaseIngestor:
    """
    Retourne l'ingestor adapté selon le type de source configuré.
    """
    source_type = (source_type or "").lower().strip()
    if source_type == "reddit":
        return RedditIngestor()
    elif source_type == "youtube":
        return YouTubeIngestor()
    else:
        # Par défaut: RSS / Atom
        return RSSIngestor()
