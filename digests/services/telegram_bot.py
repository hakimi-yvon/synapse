import logging
import httpx
from django.conf import settings
from django.contrib.auth.models import User
from digests.models import DeliveryChannel, UserPreference, Topic
from digests.tasks import generate_user_digest_task

logger = logging.getLogger(__name__)


def send_telegram_reply(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with httpx.Client(timeout=10.0) as client:
            client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
        return True
    except Exception as e:
        logger.error(f"Erreur envoi réponse Telegram: {e}")
        return False


def handle_telegram_update(update: dict) -> None:
    """
    Traite un message reçu par le bot Telegram (/start, /digest, etc.).
    """
    message = update.get("message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))
    from_user = message.get("from", {})
    username = from_user.get("username") or f"tg_{chat_id}"
    first_name = from_user.get("first_name", "Utilisateur")
    text = (message.get("text") or "").strip()

    # Trouver ou créer l'utilisateur Django correspondant
    user, _ = User.objects.get_or_create(username=username, defaults={"first_name": first_name})

    # Enregistrer ou activer le canal Telegram
    channel, _ = DeliveryChannel.objects.get_or_create(
        user=user,
        channel_type="telegram",
        defaults={"identifier": chat_id, "is_active": True},
    )
    if channel.identifier != chat_id:
        channel.identifier = chat_id
        channel.is_active = True
        channel.save(update_fields=["identifier", "is_active"])

    # Préférence utilisateur par défaut
    pref, _ = UserPreference.objects.get_or_create(
        user=user,
        defaults={"format_preference": "both", "min_importance_score": 5},
    )

    # Commandes
    if text.startswith("/start"):
        reply = (
            f"👋 *Bienvenue sur Synapse, {first_name} !*\n\n"
            "Je suis votre analyste d'actualités personnel.\n"
            "Chaque matin, je vous livre un briefing synthétique de l'actualité selon vos préférences.\n\n"
            "📌 *Commandes disponibles :*\n"
            "• `/digest` : Générer immédiatement votre briefing du jour\n"
            "• `/format audio` : Recevoir uniquement la note vocale radio\n"
            "• `/format text` : Recevoir uniquement le texte structuré\n"
            "• `/format both` : Recevoir le texte ET la note vocale\n"
            "• `/status` : Voir votre configuration actuelle"
        )
        send_telegram_reply(chat_id, reply)

    elif text.startswith("/digest"):
        send_telegram_reply(chat_id, "⏳ *Préparation de votre briefing en cours...* Je vous l'envoie dès qu'il est prêt !")
        generate_user_digest_task.delay(user.id)

    elif text.startswith("/format"):
        parts = text.split()
        if len(parts) > 1 and parts[1].lower() in ["audio", "text", "both"]:
            pref.format_preference = parts[1].lower()
            pref.save(update_fields=["format_preference"])
            send_telegram_reply(chat_id, f"✅ Votre format de réception est désormais : *{pref.format_preference}*")
        else:
            send_telegram_reply(chat_id, "Usage : `/format audio`, `/format text`, ou `/format both`")

    elif text.startswith("/status"):
        reply = (
            f"⚙️ *Votre Configuration Synapse*\n\n"
            f"• Utilisateur : `{user.username}`\n"
            f"• Format préféré : *{pref.format_preference}*\n"
            f"• Score min importance : *{pref.min_importance_score}/10*\n"
            f"• Heure de réception : *{pref.digest_hour}*\n"
            f"• Catégories : {', '.join(pref.followed_categories) if pref.followed_categories else 'Toutes'}"
        )
        send_telegram_reply(chat_id, reply)

    else:
        send_telegram_reply(chat_id, "Tapez `/digest` pour recevoir votre briefing ou `/start` pour voir les commandes.")
