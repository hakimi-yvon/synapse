import feedparser
from datetime import datetime, timezone
from celery import shared_task
from django.db import IntegrityError
from .models import Source, Article
from .embeddings import generate_embedding
from .clustering import cluster_article


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
    return f"Article '{article.title[:30]}' assigné au topic '{topic.title[:30]}'"