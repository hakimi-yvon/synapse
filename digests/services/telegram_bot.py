import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
import httpx
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from digests.models import DeliveryChannel, UserPreference, Topic
from digests.tasks import generate_user_digest_task, answer_news_question_task

logger = logging.getLogger(__name__)


def send_ask_prompt(chat_id: str) -> None:
    text = (
        "💬 *Chat with your News — Posez votre question*\n\n"
        "Je consulte en temps réel l'ensemble de nos dépêches et synthèses pour vous répondre.\n\n"
        "Exemples de questions :\n"
        "• _Que s'est-il passé de nouveau dans l'IA aujourd'hui ?_\n"
        "• _Quels sont les détails sur le nouveau modèle de code ?_\n"
        "• _Quels sont les impacts économiques majeurs ?_\n\n"
        "👉 Tapez directement votre question (ou `/cancel` pour annuler)."
    )
    send_telegram_reply(chat_id, text)


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


def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token or not callback_query_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        with httpx.Client(timeout=10.0) as client:
            client.post(url, json={"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert})
        return True
    except Exception as e:
        logger.error(f"Erreur answerCallbackQuery Telegram: {e}")
        return False


AVAILABLE_CATEGORIES = {
    "1": ("Tech", "💻 Tech & Innovations"),
    "2": ("IA", "🤖 Intelligence Artificielle"),
    "3": ("Startups", "🚀 Startups & Business"),
    "4": ("Dev", "🐍 Développement & Code"),
    "5": ("Finance", "📈 Économie & Finance"),
}

COMMON_TIMEZONES = {
    "1": ("Africa/Douala", "🇨🇲 Afrique Centrale (Douala, UTC+1)"),
    "2": ("Africa/Abidjan", "🇨🇮 Afrique de l'Ouest (Abidjan, UTC+0)"),
    "3": ("Europe/Paris", "🇫🇷 France & Europe (Paris, UTC+1/UTC+2)"),
    "4": ("Africa/Casablanca", "🇲🇦 Maroc (Casablanca, UTC+1)"),
    "5": ("America/Montreal", "🇨🇦 Canada (Montréal, UTC-5/UTC-4)"),
}


def parse_time_string(val: str) -> time | None:
    val = val.strip().lower().replace("h", ":")
    try:
        if ":" in val:
            parts = val.split(":")
            h = int(parts[0])
            m = int(parts[1]) if parts[1] else 0
        else:
            h = int(val)
            m = 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            return time(h, m)
    except Exception:
        pass
    return None


def send_time_prompt(chat_id: str) -> None:
    text = (
        "⏰ *Programmation de votre Réveil Matinal*\n\n"
        "À quelle heure souhaitez-vous recevoir votre briefing chaque matin ?\n\n"
        "👉 Répondez avec l'heure souhaitée (ex: *07:00*, *07:30*, ou *8h*).\n"
        "Tapez `/cancel` pour annuler."
    )
    send_telegram_reply(chat_id, text)


def send_timezone_prompt(chat_id: str) -> None:
    lines = ["🌍 *Choisissez votre fuseau horaire :*\n"]
    for num, (_, label) in COMMON_TIMEZONES.items():
        lines.append(f"{num}. {label}")
    lines.append("6. ✏️ Autre (tapez le fuseau IANA de votre choix, ex: `America/New_York`)")
    lines.append("\n👉 Répondez avec le *numéro* (ex: 1) ou le *nom* du fuseau.\nTapez `/cancel` pour annuler.")
    send_telegram_reply(chat_id, "\n".join(lines))


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
    Traite un message ou callback query reçu par le bot Telegram avec gestion d'état conversationnel.
    """
    # 1. Gestion des clics sur les boutons inline (Feedback 👍 / 👎)
    callback_query = update.get("callback_query")
    if callback_query:
        cb_id = str(callback_query.get("id"))
        cb_from = callback_query.get("from", {})
        cb_user_id = str(cb_from.get("id"))
        cb_username = cb_from.get("username") or f"tg_{cb_user_id}"
        cb_data = callback_query.get("data", "")

        user, _ = User.objects.get_or_create(username=cb_username)

        if cb_data.startswith("fb:"):
            parts = cb_data.split(":")
            if len(parts) == 4:
                target_type = parts[1]
                target_id = int(parts[2])
                score = int(parts[3])

                from digests.services.recommendation import process_user_feedback
                digest_id = target_id if target_type == "dig" else None
                topic_id = target_id if target_type == "top" else None

                _, msg = process_user_feedback(user, score, digest_id=digest_id, topic_id=topic_id)
                answer_callback_query(cb_id, text=msg[:190])

                chat = callback_query.get("message", {}).get("chat", {})
                chat_id = str(chat.get("id", cb_user_id))
                send_telegram_reply(chat_id, f"🎯 *Feedback enregistré :*\n{msg}")
                return

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
                f"⏰ *Réveil matinal automatique* : programmé à *{pref.digest_hour.strftime('%H:%M')}* ({pref.timezone}).\n"
                "Tapez `/heure` ou `/fuseau` pour modifier l'horaire.\n\n"
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
                f"⏰ *Réveil matinal automatique* : programmé à *{pref.digest_hour.strftime('%H:%M')}* ({pref.timezone}).\n"
                "Tapez `/heure` ou `/fuseau` pour modifier l'horaire.\n\n"
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
        send_telegram_reply(
            chat_id,
            f"✅ *Sujet configuré : {clean_kw}* !\n"
            f"⏰ Réveil automatique prévu chaque matin à *{pref.digest_hour.strftime('%H:%M')}* ({pref.timezone}).\n\n"
            "Tapez `/digest` pour tester votre briefing."
        )
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
            f"⏰ *Réveil matinal automatique* : programmé à *{pref.digest_hour.strftime('%H:%M')}* ({pref.timezone}).\n"
            "Tapez `/heure` ou `/fuseau` pour modifier l'horaire.\n\n"
            "Votre briefing combinera ces différents domaines.\n"
            "📌 Tapez `/digest` pour lancer votre briefing sur mesure !"
        )
        send_telegram_reply(chat_id, reply)
        return

    # Machine à états : Réglage de l'heure du réveil matinal
    if state == "awaiting_digest_hour":
        parsed = parse_time_string(text)
        if parsed:
            pref.digest_hour = parsed
            pref.conversation_state = ""
            pref.save(update_fields=["digest_hour", "conversation_state"])
            send_telegram_reply(
                chat_id,
                f"⏰ *Heure de réveil enregistrée !*\n\n"
                f"Votre briefing vous sera automatiquement livré chaque matin à *{parsed.strftime('%H:%M')}* (fuseau : *{pref.timezone}*).\n"
                "Tapez `/digest` pour tester immédiatement votre briefing."
            )
            return
        else:
            send_telegram_reply(
                chat_id,
                "⚠️ Format d'heure non reconnu. Répondez par exemple : *07:30*, *08:00* ou *8h* (ou tapez `/cancel` pour annuler)."
            )
            return

    # Machine à états : Choix du fuseau horaire
    if state == "awaiting_timezone":
        chosen_tz = None
        clean_tz = text.strip()
        if clean_tz in COMMON_TIMEZONES:
            chosen_tz = COMMON_TIMEZONES[clean_tz][0]
        else:
            try:
                ZoneInfo(clean_tz)
                chosen_tz = clean_tz
            except Exception:
                for _, (tz_id, label) in COMMON_TIMEZONES.items():
                    if clean_tz.lower() in label.lower() or clean_tz.lower() in tz_id.lower():
                        chosen_tz = tz_id
                        break

        if chosen_tz:
            pref.timezone = chosen_tz
            pref.conversation_state = ""
            pref.save(update_fields=["timezone", "conversation_state"])
            try:
                cur_local = datetime.now(ZoneInfo(chosen_tz)).strftime("%H:%M")
            except Exception:
                cur_local = "--:--"
            send_telegram_reply(
                chat_id,
                f"🌍 *Fuseau horaire enregistré : {chosen_tz}* !\n\n"
                f"Heure locale actuelle : *{cur_local}*.\n"
                f"Votre réveil matinal de *{pref.digest_hour.strftime('%H:%M')}* est désormais basé sur ce fuseau."
            )
            return
        else:
            send_telegram_reply(
                chat_id,
                "⚠️ Fuseau horaire non reconnu. Répondez avec un chiffre (ex: *1* à *5*) ou un fuseau IANA valide (ex: `Africa/Douala`, `Europe/Paris`)."
            )
            return

    # Machine à états : Question sur l'actualité (Chat with your News)
    if state == "awaiting_news_question":
        pref.conversation_state = ""
        pref.save(update_fields=["conversation_state"])
        send_telegram_reply(chat_id, "🔍 *Recherche et analyse des actualités en cours...* Je vous réponds dans quelques secondes.")
        answer_news_question_task.delay(user.id, chat_id, text)
        return

    # 7. Commande /digest
    if text.startswith("/digest"):
        send_telegram_reply(chat_id, "⏳ *Préparation de votre briefing en cours...* Je vous l'envoie dès qu'il est prêt !")
        generate_user_digest_task.delay(user.id)
        return

    # 8. Commande /ask ou /chat (Chat with your News)
    if text.startswith("/ask") or text.startswith("/chat"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            question = parts[1].strip()
            send_telegram_reply(chat_id, "🔍 *Recherche et analyse des dépêches en cours...* Je vous réponds dans un instant.")
            answer_news_question_task.delay(user.id, chat_id, question)
            return
        else:
            pref.conversation_state = "awaiting_news_question"
            pref.save(update_fields=["conversation_state"])
            send_ask_prompt(chat_id)
            return

    # 9. Commande /reset ou /clear (Effacer l'historique du chat)
    if text.startswith("/reset") or text.startswith("/clear"):
        cache.delete(f"news_chat_history:{user.id}")
        send_telegram_reply(chat_id, "🧹 *Historique de conversation réinitialisé.* Vous pouvez poser une nouvelle question !")
        return

    # 10. Commande /heure ou /time
    if text.startswith("/heure") or text.startswith("/time"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            parsed = parse_time_string(parts[1])
            if parsed:
                pref.digest_hour = parsed
                pref.save(update_fields=["digest_hour"])
                send_telegram_reply(
                    chat_id,
                    f"⏰ Réveil matinal mis à jour : envoi quotidien à *{parsed.strftime('%H:%M')}* (fuseau : *{pref.timezone}*)."
                )
                return
            else:
                send_telegram_reply(
                    chat_id,
                    "⚠️ Format d'heure invalide. Exemples : `/heure 07:30`, `/heure 8h00`, `/heure 8h`."
                )
                return
        else:
            pref.conversation_state = "awaiting_digest_hour"
            pref.save(update_fields=["conversation_state"])
            send_time_prompt(chat_id)
            return

    # 11. Commande /fuseau ou /timezone
    if text.startswith("/fuseau") or text.startswith("/timezone"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            input_tz = parts[1].strip()
            try:
                ZoneInfo(input_tz)
                pref.timezone = input_tz
                pref.save(update_fields=["timezone"])
                cur_local = datetime.now(ZoneInfo(input_tz)).strftime("%H:%M")
                send_telegram_reply(
                    chat_id,
                    f"🌍 Fuseau horaire mis à jour : *{input_tz}* (heure locale : *{cur_local}*)."
                )
                return
            except Exception:
                send_telegram_reply(
                    chat_id,
                    "⚠️ Fuseau horaire invalide. Exemples : `/fuseau Africa/Douala`, `/fuseau Europe/Paris`."
                )
                return
        else:
            pref.conversation_state = "awaiting_timezone"
            pref.save(update_fields=["conversation_state"])
            send_timezone_prompt(chat_id)
            return

    # 12. Commande /format
    if text.startswith("/format"):
        parts = text.split()
        if len(parts) > 1 and parts[1].lower() in ["audio", "text", "both"]:
            pref.format_preference = parts[1].lower()
            pref.save(update_fields=["format_preference"])
            send_telegram_reply(chat_id, f"✅ Votre format de réception est désormais : *{pref.format_preference}*")
        else:
            send_telegram_reply(chat_id, "Usage : `/format audio`, `/format text`, ou `/format both`")
        return

    # 13. Commande /alertes ou /alerts (Breaking News)
    if text.startswith("/alertes") or text.startswith("/alerts"):
        parts = text.split()
        if len(parts) > 1:
            sub = parts[1].lower()
            if sub in ["on", "oui", "true", "active", "activer"]:
                pref.receive_breaking_alerts = True
                pref.save(update_fields=["receive_breaking_alerts"])
                send_telegram_reply(
                    chat_id,
                    "🚨 *Alertes Breaking News activées !*\nVous recevrez en temps réel les actualités critiques majeures."
                )
                return
            elif sub in ["off", "non", "false", "desactive", "désactiver", "stop"]:
                pref.receive_breaking_alerts = False
                pref.save(update_fields=["receive_breaking_alerts"])
                send_telegram_reply(
                    chat_id,
                    "🔕 *Alertes Breaking News désactivées.*\nVous recevrez uniquement votre briefing matinal."
                )
                return
        # Pas d'argument ou argument d'aide
        state_str = "Activées 🔔" if pref.receive_breaking_alerts else "Désactivées 🔕"
        msg = (
            f"🚨 *Statut des alertes Breaking News :* {state_str}\n\n"
            "Pour modifier votre réglage :\n"
            "• `/alertes on` : Activer les alertes urgentes immédiates\n"
            "• `/alertes off` : Désactiver les alertes urgentes"
        )
        send_telegram_reply(chat_id, msg)
        return

    # 14. Commande /like, /dislike ou /feedback
    if text.startswith("/like") or text.startswith("/dislike") or text.startswith("/feedback"):
        score = 1 if (text.startswith("/like") or "👍" in text) else (-1 if (text.startswith("/dislike") or "👎" in text) else 0)
        if score != 0:
            last_digest = user.digests.order_by("-date").first()
            from digests.services.recommendation import process_user_feedback
            _, msg = process_user_feedback(user, score, digest_id=last_digest.id if last_digest else None)
            send_telegram_reply(chat_id, msg)
            return
        else:
            send_telegram_reply(
                chat_id,
                "💬 *Votre avis affine vos briefings :*\n\n"
                "• Tapez `/like` (ou 👍) si le dernier briefing correspondait à vos attentes.\n"
                "• Tapez `/dislike` (ou 👎) si vous souhaitez moins d'articles de ce style.\n"
                "• Vous pouvez aussi cliquer directement sur les boutons sous chaque briefing !"
            )
            return

    # 15. Commande /status
    if text.startswith("/status"):
        cats = [label for _, (code, label) in AVAILABLE_CATEGORIES.items() if code in pref.followed_categories]
        cats_str = ", ".join(cats) if cats else ("Tous les domaines" if not pref.keywords else "Aucune catégorie standard")
        kws_str = ", ".join(pref.keywords) if pref.keywords else "Aucun"
        has_learned = "Personnalisé ✨" if pref.interest_vector else "Standard (en attente de feedback)"
        try:
            cur_local = datetime.now(ZoneInfo(pref.timezone or "Africa/Douala")).strftime("%H:%M")
        except Exception:
            cur_local = "--:--"

        reply = (
            f"⚙️ *Votre Configuration Synapse*\n\n"
            f"• Utilisateur : `{user.username}`\n"
            f"• Profil d'apprentissage : *{has_learned}*\n"
            f"• Format : *{pref.format_preference}*\n"
            f"• Domaines suivis : *{cats_str}*\n"
            f"• Mots-clés : *{kws_str}*\n"
            f"• Score d'importance min : *{pref.min_importance_score}/10*\n"
            f"• ⏰ Réveil automatique : *{pref.digest_hour.strftime('%H:%M')}*\n"
            f"• 🌍 Fuseau horaire : *{pref.timezone}* (heure locale : *{cur_local}*)\n"
            f"• 🚨 Flashs Breaking News : *{'Activés 🔔' if pref.receive_breaking_alerts else 'Désactivés 🔕'}*\n\n"
            "💡 *Commandes disponibles :*\n"
            "• `/like` / `/dislike` : Noter le dernier briefing (apprentissage vectoriel)\n"
            "• `/ask [question]` : Poser une question sur l'actualité (Chat with your News)\n"
            "• `/alertes [on|off]` : Activer/désactiver les alertes d'urgence\n"
            "• `/digest` : Recevoir votre briefing maintenant\n"
            "• `/heure` : Modifier l'heure de livraison matinale\n"
            "• `/fuseau` : Changer de fuseau horaire\n"
            "• `/topics` : Modifier vos thématiques d'actualités\n"
            "• `/format` : Changer le format (text, audio, both)\n"
            "• `/reset` : Réinitialiser la mémoire de discussion"
        )
        send_telegram_reply(chat_id, reply)
        return

    # Traitement conversationnel par défaut : si texte libre non-commande, répondre à la question
    if not text.startswith("/") and len(text) >= 3:
        send_telegram_reply(chat_id, "🔍 *Analyse des actualités en cours...*")
        answer_news_question_task.delay(user.id, chat_id, text)
        return

    # Message par défaut si texte vide ou commande inconnue
    send_telegram_reply(
        chat_id,
        "💡 *Comment utiliser Synapse :*\n\n"
        "• Posez-moi directement une question sur l'actualité (ex: _Quelles nouvelles sur OpenAI ?_)\n"
        "• `/ask` : Poser une question d'approfondissement\n"
        "• `/digest` : Générer et recevoir votre briefing personnalisé\n"
        "• `/heure` : Modifier l'heure du réveil matinal\n"
        "• `/topics` : Configurer vos centres d'intérêt\n"
        "• `/status` : Voir votre configuration actuelle"
    )

