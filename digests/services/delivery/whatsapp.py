import logging
import httpx
from django.conf import settings
from digests.models import Digest, DeliveryChannel
from .base import BaseDeliveryService

logger = logging.getLogger(__name__)


class WhatsAppDeliveryService(BaseDeliveryService):
    """
    Service d'envoi WhatsApp supportant Twilio et Meta WhatsApp Cloud API.
    """

    def __init__(self):
        self.provider = getattr(settings, "WHATSAPP_PROVIDER", "twilio").lower()

    def send_digest(self, digest: Digest, channel: DeliveryChannel) -> tuple[bool, str]:
        recipient = channel.identifier.strip()
        pref = getattr(digest.user, "preference", None)
        format_pref = pref.format_preference if pref else "both"

        text_body = digest.script_text[:1600] if digest.script_text else "Votre briefing Synapse est prêt."

        if self.provider == "meta":
            return self._send_via_meta(digest, recipient, text_body, format_pref)
        else:
            return self._send_via_twilio(digest, recipient, text_body, format_pref)

    def _send_via_twilio(self, digest: Digest, recipient: str, text: str, format_pref: str) -> tuple[bool, str]:
        account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        from_number = getattr(settings, "TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

        if not account_sid or not auth_token:
            err = "TWILIO_ACCOUNT_SID ou TWILIO_AUTH_TOKEN non configuré"
            logger.warning(err)
            return False, err

        to_number = recipient if recipient.startswith("whatsapp:") else f"whatsapp:{recipient}"

        data = {
            "From": from_number,
            "To": to_number,
            "Body": text,
        }

        # Si l'audio est présent et accessible en ligne, on l'ajoute comme MediaUrl
        if format_pref in ["audio", "both"] and digest.audio_url and digest.audio_url.startswith("http"):
            data["MediaUrl"] = digest.audio_url

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, data=data, auth=(account_sid, auth_token))
                if res.status_code in [200, 201]:
                    return True, ""
                return False, f"Erreur Twilio ({res.status_code}): {res.text}"
        except Exception as e:
            err_msg = f"Exception envoi Twilio WhatsApp: {str(e)}"
            logger.error(err_msg)
            return False, err_msg

    def _send_via_meta(self, digest: Digest, recipient: str, text: str, format_pref: str) -> tuple[bool, str]:
        token = getattr(settings, "META_WHATSAPP_TOKEN", None)
        phone_id = getattr(settings, "META_WHATSAPP_PHONE_NUMBER_ID", None)

        if not token or not phone_id:
            err = "META_WHATSAPP_TOKEN ou META_WHATSAPP_PHONE_NUMBER_ID non configuré"
            logger.warning(err)
            return False, err

        # Nettoyage du numéro de téléphone (uniquement chiffres)
        clean_recipient = "".join(filter(str.isdigit, recipient))
        url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": clean_recipient,
                    "type": "text",
                    "text": {"body": text},
                }
                res = client.post(url, headers=headers, json=payload)
                if res.status_code in [200, 201]:
                    return True, ""
                return False, f"Erreur Meta WhatsApp ({res.status_code}): {res.text}"
        except Exception as e:
            err_msg = f"Exception envoi Meta WhatsApp: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
