from abc import ABC, abstractmethod
from digests.models import Digest, DeliveryChannel


class BaseDeliveryService(ABC):
    @abstractmethod
    def send_digest(self, digest: Digest, channel: DeliveryChannel) -> tuple[bool, str]:
        """
        Envoie un digest sur le canal spécifié.
        Retourne un tuple (succès: bool, message_erreur: str).
        """
        pass
