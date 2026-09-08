import feedparser
from datetime import datetime, timezone
from celery import shared_task
from .models import Source, Article


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

        Article.objects.create(
            source=source,
            title=entry.get("title", "Sans titre"),
            url=url,
            raw_content=entry.get("summary", ""),
            published_at=published_at,
        )
        created_count += 1

    source.last_fetched_at = datetime.now(timezone.utc)
    source.save(update_fields=["last_fetched_at"])

    return f"{created_count} nouveaux articles depuis {source.name}"


@shared_task
def fetch_all_sources():
    source_ids = Source.objects.filter(is_active=True).values_list("id", flat=True)
    for source_id in source_ids:
        fetch_source.delay(source_id)
    return f"{len(source_ids)} sources mises en file d'attente"