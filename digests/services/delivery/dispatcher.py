import logging
from digests.models import Digest, DigestDelivery
from .telegram import TelegramDeliveryService
from .whatsapp import WhatsAppDeliveryService

logger = logging.getLogger(__name__)


def dispatch_digest_to_channels(digest: Digest) -> list[DigestDelivery]:
    """
    Parcourt tous les canaux de diffusion actifs configurés pour l'utilisateur
    et distribue le digest (audio et/ou texte).
    Enregistre le statut (sent ou failed) dans la table DigestDelivery.
    """
    active_channels = digest.user.delivery_channels.filter(is_active=True)
    deliveries = []

    telegram_service = TelegramDeliveryService()
    whatsapp_service = WhatsAppDeliveryService()

    for channel in active_channels:
        delivery, _ = DigestDelivery.objects.update_or_create(
            digest=digest,
            channel=channel,
            defaults={"status": "pending", "error_message": ""},
        )

        success = False
        error_msg = ""

        if channel.channel_type == "telegram":
            success, error_msg = telegram_service.send_digest(digest, channel)
        elif channel.channel_type == "whatsapp":
            success, error_msg = whatsapp_service.send_digest(digest, channel)
        else:
            error_msg = f"Canal non supporté pour la diffusion automatique : {channel.channel_type}"

        delivery.status = "sent" if success else "failed"
        delivery.error_message = error_msg
        delivery.save(update_fields=["status", "error_message"])

        deliveries.append(delivery)
        logger.info(f"Digest {digest.id} envoyé via {channel.channel_type} ({channel.identifier}) : {delivery.status}")

    return deliveries
