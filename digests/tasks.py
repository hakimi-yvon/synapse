from datetime import datetime, timezone
from celery import shared_task
from django.db import IntegrityError
from .models import Source, Article, Topic, Digest, UserPreference
from .embeddings import generate_embedding
from .clustering import cluster_article
from .services.synthesizer import summarize_topic, generate_digest_script
from .ingestors import get_ingestor


@shared_task
def fetch_source(source_id):
    try:
        source = Source.objects.get(id=source_id, is_active=True)
    except Source.DoesNotExist:
        return f"Source {source_id} introuvable ou inactive"

    ingestor = get_ingestor(source.source_type)
    raw_articles = ingestor.fetch(source)
    created_count = 0

    for raw in raw_articles:
        if not raw.url:
            continue

        if Article.objects.filter(url=raw.url).exists():
            continue

        try:
            article = Article.objects.create(
                source=source,
                title=raw.title,
                url=raw.url,
                raw_content=raw.raw_content,
                published_at=raw.published_at,
            )
            created_count += 1
            embed_article.delay(article.id)
        except IntegrityError:
            # En cas de doublon concurrent sur l'URL
            continue

    source.last_fetched_at = datetime.now(timezone.utc)
    source.save(update_fields=["last_fetched_at"])

    return f"{created_count} nouveaux articles depuis {source.name} [{source.source_type}]"


@shared_task
def fetch_all_sources():
    source_ids = Source.objects.filter(is_active=True).values_list("id", flat=True)
    for source_id in source_ids:
        fetch_source.delay(source_id)
    return f"{len(source_ids)} sources mises en file d'attente"


@shared_task
def embed_article(article_id):
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        return f"Article {article_id} introuvable"

    if article.embedding is not None:
        return f"Article {article_id} a déjà un embedding"

    text = f"{article.title}\n{article.raw_content}"[:2000]  # on limite la taille
    article.embedding = generate_embedding(text)
    article.save(update_fields=["embedding"])

    # Enchaînement asynchrone du clustering sémantique
    cluster_article_task.delay(article.id)

    return f"Embedding généré pour: {article.title}"


@shared_task
def cluster_article_task(article_id):
    try:
        article = Article.objects.get(id=article_id)
    except Article.DoesNotExist:
        return f"Article {article_id} introuvable"

    topic = cluster_article(article)
    # Déclencher la synthèse LLM du topic mis à jour
    summarize_topic_task.delay(topic.id)
    return f"Article '{article.title[:30]}' assigné au topic '{topic.title[:30]}'"


@shared_task
def summarize_topic_task(topic_id):
    try:
        topic = Topic.objects.get(id=topic_id)
    except Topic.DoesNotExist:
        return f"Topic {topic_id} introuvable"

    result = summarize_topic(topic)
    topic.refresh_from_db()

    # Détection automatique et diffusion immédiate d'une alerte Breaking News
    if (topic.is_breaking_news or topic.importance_score >= 9) and not topic.alert_sent_at:
        dispatch_breaking_news_alert_task.delay(topic.id)

    return f"Topic {topic_id} résumé: {result.get('title')[:40]}"


@shared_task
def dispatch_breaking_news_alert_task(topic_id):
    """
    Diffuse une alerte Breaking News en temps réel aux utilisateurs éligibles
    ayant activé les alertes et suivant la catégorie concernée.
    """
    import logging
    from django.utils import timezone
    from .models import Topic, UserPreference
    from .services.telegram_bot import send_telegram_reply
    from .services.delivery.whatsapp import send_whatsapp_message

    logger = logging.getLogger(__name__)

    try:
        topic = Topic.objects.get(id=topic_id)
    except Topic.DoesNotExist:
        return f"Topic {topic_id} introuvable"

    if topic.alert_sent_at is not None:
        return f"Alerte déjà envoyée pour le topic {topic_id}"

    # Verrouillage pour éviter les doublons d'envoi
    topic.alert_sent_at = timezone.now()
    topic.save(update_fields=["alert_sent_at"])

    bullets = "\n".join(f"• {b}" for b in topic.summary_bullets[:3]) if topic.summary_bullets else ""
    alert_text = (
        "🚨 *ALERTE BREAKING NEWS* 🚨\n\n"
        f"🔥 *{topic.title}*\n"
        f"🏷️ Thématique : *{topic.category or 'Actualité'}*\n\n"
        f"{bullets}\n\n"
        f"⚡ Indice d'importance : *{topic.importance_score}/10*\n\n"
        f"💬 _Approfondir ce sujet avec l'analyste :_\n`/ask {topic.title[:50]}`"
    )

    eligible_prefs = UserPreference.objects.filter(
        receive_breaking_alerts=True,
        min_importance_score__lte=topic.importance_score,
    ).select_related("user")

    sent_count = 0
    for pref in eligible_prefs:
        if pref.followed_categories and topic.category not in pref.followed_categories:
            continue

        channels = pref.user.delivery_channels.filter(is_active=True)
        for ch in channels:
            if ch.channel_type == "telegram":
                if send_telegram_reply(ch.identifier, alert_text):
                    sent_count += 1
            elif ch.channel_type == "whatsapp":
                clean_txt = alert_text.replace("*", "").replace("_", "")
                if send_whatsapp_message(ch.identifier, clean_txt):
                    sent_count += 1

    return f"Alerte Breaking News envoyée pour le topic {topic.id} ({sent_count} canaux notifiés)"


@shared_task
def generate_user_digest_task(user_id, target_date=None):
    from datetime import date, timedelta
    from django.contrib.auth.models import User
    from django.db.models import Q

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return f"User {user_id} introuvable"

    pref = getattr(user, "preference", None)
    if not pref:
        return f"Aucune préférence configurée pour {user.username}"

    digest_date = target_date or date.today()

    # Topics des dernières 24h
    window_start = datetime.now(timezone.utc) - timedelta(hours=24)
    topics_qs = Topic.objects.filter(
        created_at__gte=window_start,
        importance_score__gte=pref.min_importance_score,
    )

    # Filtrage par catégories si spécifiées
    if pref.followed_categories:
        topics_qs = topics_qs.filter(category__in=pref.followed_categories)

    # Filtrage par mots-clés si spécifiés
    if pref.keywords:
        keyword_query = Q()
        for kw in pref.keywords:
            keyword_query |= Q(title__icontains=kw)
        topics_qs = topics_qs.filter(keyword_query)

    if pref.interest_vector:
        from pgvector.django import CosineDistance
        topics = list(
            topics_qs.filter(centroid_embedding__isnull=False)
            .annotate(dist_pref=CosineDistance("centroid_embedding", pref.interest_vector))
            .order_by("dist_pref", "-importance_score")[:7]
        )
    else:
        topics = list(topics_qs.order_by("-importance_score")[:7])

    if not topics:
        # Fallback : si aucun sujet dans les 24h, récupérer les plus récents disponibles en base
        fallback_qs = Topic.objects.filter(importance_score__gte=pref.min_importance_score)
        if pref.followed_categories:
            fallback_qs = fallback_qs.filter(category__in=pref.followed_categories)
        if pref.keywords:
            fallback_qs = fallback_qs.filter(keyword_query)
        if pref.interest_vector:
            from pgvector.django import CosineDistance
            topics = list(
                fallback_qs.filter(centroid_embedding__isnull=False)
                .annotate(dist_pref=CosineDistance("centroid_embedding", pref.interest_vector))
                .order_by("dist_pref", "-created_at", "-importance_score")[:7]
            )
        else:
            topics = list(fallback_qs.order_by("-created_at", "-importance_score")[:7])

    if not topics:
        from .services.telegram_bot import send_telegram_reply
        tg_channel = user.delivery_channels.filter(channel_type="telegram", is_active=True).first()
        if tg_channel:
            send_telegram_reply(
                tg_channel.identifier,
                "ℹ️ *Aucune actualité n'est encore enregistrée.* Une collecte automatique a été lancée, réessayez dans 30 secondes avec `/digest` !",
            )
        fetch_all_sources.delay()
        return f"Aucun topic éligible pour {user.username} le {digest_date}"

    script = generate_digest_script(topics, format_preference=pref.format_preference)

    digest, _ = Digest.objects.update_or_create(
        user=user,
        date=digest_date,
        defaults={"script_text": script},
    )
    digest.topics.set(topics)

    # Déclencher la synthèse vocale si l'utilisateur souhaite de l'audio
    if pref.format_preference in ["audio", "both"]:
        generate_digest_audio_task.delay(digest.id)
    else:
        # Envoi direct si format texte uniquement
        deliver_digest_task.delay(digest.id)

    return f"Digest {digest_date} généré pour {user.username} avec {len(topics)} topics"


@shared_task
def generate_digest_audio_task(digest_id):
    from .services.tts import generate_audio_for_digest
    try:
        digest = Digest.objects.get(id=digest_id)
    except Digest.DoesNotExist:
        return f"Digest {digest_id} introuvable"

    try:
        audio_url = generate_audio_for_digest(digest)
        # Déclencher la diffusion maintenant que l'audio et le texte sont prêts
        deliver_digest_task.delay(digest.id)
        return f"Audio généré pour le digest {digest_id}: {audio_url}"
    except Exception as e:
        # En cas d'erreur sur l'audio, envoyer quand même le texte
        deliver_digest_task.delay(digest.id)
        return f"Erreur génération audio digest {digest_id}: {e}"


@shared_task
def deliver_digest_task(digest_id):
    from .services.delivery import dispatch_digest_to_channels
    try:
        digest = Digest.objects.get(id=digest_id)
    except Digest.DoesNotExist:
        return f"Digest {digest_id} introuvable"

    deliveries = dispatch_digest_to_channels(digest)
    sent_count = sum(1 for d in deliveries if d.status == "sent")
    return f"Digest {digest_id} distribué à {sent_count}/{len(deliveries)} canaux"


@shared_task
def dispatch_daily_digests():
    """
    Tâche de déclenchement manuel ou global qui parcourt les utilisateurs
    et lance la génération immédiate de leur briefing.
    """
    from .models import UserPreference
    users_with_prefs = UserPreference.objects.values_list("user_id", flat=True)
    for user_id in users_with_prefs:
        generate_user_digest_task.delay(user_id)
    return f"{len(users_with_prefs)} digests planifiés"


@shared_task
def dispatch_scheduled_morning_digests():
    """
    Tâche périodique (exécutée toutes les 10 minutes par Celery Beat).
    Pour chaque utilisateur :
    - Détermine l'heure actuelle dans son fuseau horaire (UserPreference.timezone).
    - Compare avec son heure de briefing programmée (UserPreference.digest_hour).
    - Si l'heure locale correspond (fenêtre de 45 min) et qu'aucun briefing
      n'a été généré pour aujourd'hui (date locale), déclenche la génération et l'envoi.
    """
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    from django.core.cache import cache
    from .models import UserPreference, Digest

    now_utc = datetime.now(timezone.utc)
    dispatched_count = 0

    prefs = UserPreference.objects.select_related("user").all()
    for pref in prefs:
        user = pref.user
        tz_name = pref.timezone or "Africa/Douala"
        try:
            user_tz = ZoneInfo(tz_name)
        except Exception:
            user_tz = ZoneInfo("Africa/Douala")

        local_now = now_utc.astimezone(user_tz)
        local_date = local_now.date()

        # Évite les déclenchements en double via le cache et la base
        cache_key = f"scheduled_digest_dispatched:{user.id}:{local_date}"
        if cache.get(cache_key):
            continue

        if Digest.objects.filter(user=user, date=local_date).exists():
            continue

        target_time = pref.digest_hour or time(7, 0)
        if isinstance(target_time, str):
            parts = target_time.split(":")
            target_time = time(int(parts[0]), int(parts[1]))

        target_dt = datetime.combine(local_date, target_time, tzinfo=user_tz)
        diff_seconds = (local_now - target_dt).total_seconds()

        # Si l'heure actuelle est dans la fenêtre [0, 45 min[ après l'heure configurée
        if 0 <= diff_seconds < 2700:
            cache.set(cache_key, True, timeout=86400)
            generate_user_digest_task.delay(user.id, target_date=local_date)
            dispatched_count += 1

    return f"{dispatched_count} briefing(s) planifié(s) déclenché(s)"


@shared_task
def answer_news_question_task(user_id: int, chat_id: str, question: str):
    """
    Exécute la recherche vectorielle et la génération IA pour répondre
    à une question d'actualité posée par l'utilisateur sur Telegram.
    """
    import logging
    from django.contrib.auth.models import User
    from .services.news_chat import answer_news_question
    from .services.telegram_bot import send_telegram_reply

    logger = logging.getLogger(__name__)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        send_telegram_reply(chat_id, "⚠️ Utilisateur introuvable.")
        return "User introuvable"

    try:
        answer = answer_news_question(user, question)
        send_telegram_reply(chat_id, answer)
        return f"Réponse fournie à {user.username} pour '{question[:30]}'"
    except Exception as e:
        logger.error(f"Erreur answer_news_question_task: {e}")
        send_telegram_reply(
            chat_id,
            "⚠️ Une erreur est survenue lors de l'analyse de votre question. Réessayez dans un instant."
        )
        return f"Erreur: {e}"