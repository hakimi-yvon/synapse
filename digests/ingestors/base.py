from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from digests.models import Source


@dataclass
class RawArticle:
    title: str
    url: str
    raw_content: str
    published_at: datetime
    source: Source


class BaseIngestor(ABC):
    @abstractmethod
    def fetch(self, source: Source) -> list[RawArticle]:
        """
        Récupère et normalise les publications d'une source en objets RawArticle.
        """
        pass
