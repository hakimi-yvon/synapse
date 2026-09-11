import logging
from pathlib import Path
import httpx
from django.conf import settings
from digests.models import Digest, DeliveryChannel
from .base import BaseDeliveryService

logger = logging.getLogger(__name__)


class TelegramDeliveryService(BaseDeliveryService):
    def __init__(self, bot_token: str = None):
        self.bot_token = bot_token or getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    def send_digest(self, digest: Digest, channel: DeliveryChannel) -> tuple[bool, str]:
        chat_id = channel.identifier
        if not self.bot_token:
            err = "TELEGRAM_BOT_TOKEN non configuré dans settings/.env"
            logger.warning(err)
            return False, err

        pref = getattr(digest.user, "preference", None)
        format_pref = pref.format_preference if pref else "both"

        try:
            with httpx.Client(timeout=30.0) as client:
                # 1. Envoi de l'audio si présent et demandé
                if format_pref in ["audio", "both"] and digest.audio_url:
                    local_audio_path = Path(settings.BASE_DIR) / digest.audio_url.lstrip("/")
                    if local_audio_path.exists():
                        with open(local_audio_path, "rb") as f:
                            files = {"audio": (local_audio_path.name, f, "audio/mpeg")}
                            data = {
                                "chat_id": chat_id,
                                "title": f"Briefing Synapse - {digest.date}",
                                "performer": "Synapse Intelligence",
                                "caption": f"🎙️ *Votre Briefing Synapse du {digest.date}*",
                                "parse_mode": "Markdown",
                            }
                            audio_res = client.post(f"{self.api_url}/sendAudio", data=data, files=files)
                            if audio_res.status_code != 200:
                                logger.warning(f"Échec envoi audio Telegram : {audio_res.text}")

                # 2. Envoi du texte structuré si demandé
                if format_pref in ["text", "both"] and digest.script_text:
                    # Telegram limite les messages à 4096 caractères
                    text = digest.script_text[:4000]
                    msg_data = {
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    }
                    res = client.post(f"{self.api_url}/sendMessage", json=msg_data)
                    # Si le Markdown échoue (ex: syntaxe particulière non échappée), repli en texte brut
                    if res.status_code != 200:
                        msg_data.pop("parse_mode")
                        res = client.post(f"{self.api_url}/sendMessage", json=msg_data)

                    if res.status_code != 200:
                        return False, f"Erreur Telegram ({res.status_code}): {res.text}"

            return True, ""

        except Exception as e:
            err_msg = f"Exception envoi Telegram: {str(e)}"
            logger.error(err_msg)
            return False, err_msg
