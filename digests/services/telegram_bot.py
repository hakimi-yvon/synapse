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


AVAILABLE_CATEGORIES = {
    "1": ("Tech", "💻 Tech & Innovations"),
    "2": ("IA", "🤖 Intelligence Artificielle"),
    "3": ("Startups", "🚀 Startups & Business"),
    "4": ("Dev", "🐍 Développement & Code"),
    "5": ("Finance", "📈 Économie & Finance"),
}


def send_scope_choice_prompt(chat_id: str) -> None:
    text = (
        "🎯 *Personnalisation de vos actualités*\n\n"
        "Souhaitez-vous recevoir l'actualité concernant :\n"
        "1️⃣ **Un seul domaine précis** (ex: uniquement l'IA)\n"
        "2️⃣ **Plusieurs domaines** (ex: Tech, IA et Startups)\n\n"
        "👉 Répondez simplement par *1* ou *2*."
    )
    send_telegram_reply(chat_id, text)


def send_single_category_prompt(chat_id: str) -> None:
    lines = ["🎯 *Choisissez votre domaine unique :*\n"]
    for num, (_, label) in AVAILABLE_CATEGORIES.items():
        lines.append(f"{num}. {label}")
    lines.append("6. ✏️ Autre (tapez directement votre mot-clé ou sujet)")
    lines.append("\n👉 Répondez avec le *numéro* (ex: 2) ou le *nom* de votre sujet.")
    send_telegram_reply(chat_id, "\n".join(lines))


def send_multiple_categories_prompt(chat_id: str) -> None:
    lines = ["🌐 *Quels domaines souhaitez-vous suivre ?*\n"]
    for num, (_, label) in AVAILABLE_CATEGORIES.items():
        lines.append(f"{num}. {label}")
    lines.append(
        "\n👉 Indiquez les numéros séparés par une virgule (ex: *1, 2, 4*) "
        "ou ajoutez vos propres mots-clés (ex: *1, 2, Cybersécurité*)."
    )
    send_telegram_reply(chat_id, "\n".join(lines))


def handle_telegram_update(update: dict) -> None:
    """
    Traite un message reçu par le bot Telegram avec gestion d'état conversationnel.
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

    # Préférence utilisateur
    pref, _ = UserPreference.objects.get_or_create(
        user=user,
        defaults={"format_preference": "both", "min_importance_score": 5},
    )

    state = pref.conversation_state

    # 1. Commande d'annulation
    if text.startswith("/cancel"):
        pref.conversation_state = ""
        pref.save(update_fields=["conversation_state"])
        send_telegram_reply(chat_id, "Configuration annulée. Tapez `/digest` pour lancer votre briefing ou `/topics` pour reconfigurer.")
        return

    # 2. Commande /start (Onboarding)
    if text.startswith("/start"):
        pref.conversation_state = "awaiting_scope_choice"
        pref.save(update_fields=["conversation_state"])

        welcome = (
            f"👋 *Bienvenue sur Synapse, {first_name} !*\n\n"
            "Je suis votre analyste d'actualités personnel.\n"
            "Chaque matin, je synthétise l'actualité selon vos goûts précis en texte et en audio.\n\n"
            "Commençons par configurer vos centres d'intérêt :"
        )
        send_telegram_reply(chat_id, welcome)
        send_scope_choice_prompt(chat_id)
        return

    # 3. Commande /topics (Reconfiguration explicite)
    if text.startswith("/topics"):
        pref.conversation_state = "awaiting_scope_choice"
        pref.save(update_fields=["conversation_state"])
        send_scope_choice_prompt(chat_id)
        return

    # 4. Machine à états : Choix d'un domaine ou plusieurs
    if state == "awaiting_scope_choice":
        clean_ans = text.lower()
        if "1" in clean_ans or "un" in clean_ans or "seul" in clean_ans:
            pref.conversation_state = "awaiting_single_category"
            pref.save(update_fields=["conversation_state"])
            send_single_category_prompt(chat_id)
            return
        elif "2" in clean_ans or "plusieur" in clean_ans or "multi" in clean_ans:
            pref.conversation_state = "awaiting_multiple_categories"
            pref.save(update_fields=["conversation_state"])
            send_multiple_categories_prompt(chat_id)
            return
        else:
            send_telegram_reply(chat_id, "Veuillez répondre par *1* (un seul domaine) ou *2* (plusieurs domaines).")
            return

    # 5. Machine à états : Sélection d'un domaine UNIQUE
    if state == "awaiting_single_category":
        clean_text = text.strip()
        chosen_cat = None
        chosen_label = None

        if clean_text in AVAILABLE_CATEGORIES:
            chosen_cat, chosen_label = AVAILABLE_CATEGORIES[clean_text]
        elif clean_text == "6":
            send_telegram_reply(chat_id, "Tapez le nom de votre sujet ou mot-clé personnalisé (ex: *Cybersécurité*, *Biotech*) :")
            pref.conversation_state = "awaiting_custom_keyword_single"
            pref.save(update_fields=["conversation_state"])
            return
        else:
            # Recherche par mot-clé textuel
            for _, (cat_code, label) in AVAILABLE_CATEGORIES.items():
                if clean_text.lower() in label.lower() or clean_text.lower() == cat_code.lower():
                    chosen_cat = cat_code
                    chosen_label = label
                    break

        if chosen_cat:
            pref.followed_categories = [chosen_cat]
            pref.keywords = []
            pref.conversation_state = ""
            pref.save(update_fields=["followed_categories", "keywords", "conversation_state"])
            reply = (
                f"✅ *Domaine unique configuré : {chosen_label}* !\n\n"
                "Vos prochains briefings contiendront uniquement l'actualité de ce secteur.\n\n"
                "📌 Tapez `/digest` pour recevoir immédiatement votre briefing personnalisé !"
            )
            send_telegram_reply(chat_id, reply)
            return
        else:
            # C'est un mot-clé libre entré directement
            pref.followed_categories = []
            pref.keywords = [clean_text]
            pref.conversation_state = ""
            pref.save(update_fields=["followed_categories", "keywords", "conversation_state"])
            reply = (
                f"✅ *Sujet personnalisé configuré : {clean_text}* !\n\n"
                "Vos prochains briefings cibleront cette thématique.\n\n"
                "📌 Tapez `/digest` pour lancer la génération !"
            )
            send_telegram_reply(chat_id, reply)
            return

    if state == "awaiting_custom_keyword_single":
        clean_kw = text.strip()
        pref.followed_categories = []
        pref.keywords = [clean_kw]
        pref.conversation_state = ""
        pref.save(update_fields=["followed_categories", "keywords", "conversation_state"])
        send_telegram_reply(chat_id, f"✅ *Sujet configuré : {clean_kw}* !\nTapez `/digest` pour tester votre briefing.")
        return

    # 6. Machine à états : Sélection de PLUSIEURS domaines
    if state == "awaiting_multiple_categories":
        raw_items = [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
        selected_cats = []
        selected_labels = []
        custom_kws = []

        for item in raw_items:
            if item in AVAILABLE_CATEGORIES:
                cat_code, label = AVAILABLE_CATEGORIES[item]
                if cat_code not in selected_cats:
                    selected_cats.append(cat_code)
                    selected_labels.append(label)
            else:
                # Vérifier si c'est un nom de catégorie connu
                matched = False
                for _, (cat_code, label) in AVAILABLE_CATEGORIES.items():
                    if item.lower() in label.lower() or item.lower() == cat_code.lower():
                        if cat_code not in selected_cats:
                            selected_cats.append(cat_code)
                            selected_labels.append(label)
                        matched = True
                        break
                if not matched:
                    custom_kws.append(item)

        if not selected_cats and not custom_kws:
            send_telegram_reply(chat_id, "Je n'ai pas compris votre sélection. Répondez avec des numéros (ex: *1, 2, 4*) ou tapez vos mots-clés.")
            return

        pref.followed_categories = selected_cats
        pref.keywords = custom_kws
        pref.conversation_state = ""
        pref.save(update_fields=["followed_categories", "keywords", "conversation_state"])

        summary_parts = selected_labels + [f"🔑 `{kw}`" for kw in custom_kws]
        reply = (
            "✅ *Vos préférences multiples ont été enregistrées avec succès !*\n\n"
            f"📋 *Domaines sélectionnés :*\n• " + "\n• ".join(summary_parts) + "\n\n"
            "Votre briefing combinera ces différents domaines.\n"
            "📌 Tapez `/digest` pour lancer votre briefing sur mesure !"
        )
        send_telegram_reply(chat_id, reply)
        return

    # 7. Commande /digest
    if text.startswith("/digest"):
        send_telegram_reply(chat_id, "⏳ *Préparation de votre briefing en cours...* Je vous l'envoie dès qu'il est prêt !")
        generate_user_digest_task.delay(user.id)
        return

    # 8. Commande /format
    if text.startswith("/format"):
        parts = text.split()
        if len(parts) > 1 and parts[1].lower() in ["audio", "text", "both"]:
            pref.format_preference = parts[1].lower()
            pref.save(update_fields=["format_preference"])
            send_telegram_reply(chat_id, f"✅ Votre format de réception est désormais : *{pref.format_preference}*")
        else:
            send_telegram_reply(chat_id, "Usage : `/format audio`, `/format text`, ou `/format both`")
        return

    # 9. Commande /status
    if text.startswith("/status"):
        cats = [label for _, (code, label) in AVAILABLE_CATEGORIES.items() if code in pref.followed_categories]
        cats_str = ", ".join(cats) if cats else ("Tous les domaines" if not pref.keywords else "Aucune catégorie standard")
        kws_str = ", ".join(pref.keywords) if pref.keywords else "Aucun"

        reply = (
            f"⚙️ *Votre Configuration Synapse*\n\n"
            f"• Utilisateur : `{user.username}`\n"
            f"• Format : *{pref.format_preference}*\n"
            f"• Domaines suivis : *{cats_str}*\n"
            f"• Mots-clés : *{kws_str}*\n"
            f"• Score d'importance min : *{pref.min_importance_score}/10*\n\n"
            "💡 Tapez `/topics` pour modifier vos domaines ou `/format` pour changer le format."
        )
        send_telegram_reply(chat_id, reply)
        return

    # Message par défaut
    send_telegram_reply(
        chat_id,
        "Tapez `/digest` pour recevoir votre briefing, `/topics` pour changer vos domaines d'intérêt, ou `/status` pour voir vos réglages."
    )

