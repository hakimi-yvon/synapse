import feedparser
from datetime import datetime, timezone
from celery import shared_task
from django.db import IntegrityError
from .models import Source, Article, Topic, Digest, UserPreference
from .embeddings import generate_embedding
from .clustering import cluster_article
from .services.synthesizer import summarize_topic, generate_digest_script


@shared_task
def fetch_source(source_id):
    try:
        source = Source.objects.get(id=source_id, is_active=True)
    except Source.DoesNotExist:
        return f"Source {source_id} introuvable ou inactive"

    feed = feedparser.parse(source.url)
    created_count = 0

    for entry in feed.entries:
        url = entry.get("link")
        if not url:
            continue

        if Article.objects.filter(url=url).exists():
            continue

        published = entry.get("published_parsed")
        published_at = (
            datetime(*published[:6], tzinfo=timezone.utc)
            if published else datetime.now(timezone.utc)
        )

        try:
            article = Article.objects.create(
                source=source,
                title=entry.get("title", "Sans titre"),
                url=url,
                raw_content=entry.get("summary", ""),
                published_at=published_at,
            )
            created_count += 1
            embed_article.delay(article.id)
        except IntegrityError:
            # En cas de doublon concurrent sur l'URL
            continue

    source.last_fetched_at = datetime.now(timezone.utc)
    source.save(update_fields=["last_fetched_at"])

    return f"{created_count} nouveaux articles depuis {source.name}"


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
    return f"Topic {topic_id} résumé: {result.get('title')[:40]}"


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

    topics = list(topics_qs.order_by("-importance_score")[:7])
    if not topics:
        return f"Aucun topic éligible pour {user.username} le {digest_date}"

    script = generate_digest_script(topics, format_preference=pref.format_preference)

    digest, _ = Digest.objects.update_or_create(
        user=user,
        date=digest_date,
        defaults={"script_text": script},
    )
    digest.topics.set(topics)

    return f"Digest {digest_date} généré pour {user.username} avec {len(topics)} topics"


@shared_task
def dispatch_daily_digests():
    """
    Tâche périodique qui parcourt les utilisateurs ayant des préférences
    et lance la génération de leur briefing.
    """
    from .models import UserPreference
    users_with_prefs = UserPreference.objects.values_list("user_id", flat=True)
    for user_id in users_with_prefs:
        generate_user_digest_task.delay(user_id)
    return f"{len(users_with_prefs)} digests planifiés"