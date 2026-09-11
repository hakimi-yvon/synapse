import numpy as np
from datetime import timedelta
from django.utils import timezone
from pgvector.django import CosineDistance
from .models import Article, Topic


def recalculate_topic_centroid(topic: Topic) -> None:
    """
    Recalcule et met à jour le centroïde vectoriel (unitaire) du Topic
    en moyennant les embeddings de tous ses articles associés.
    """
    embeddings = list(
        topic.article_set.filter(embedding__isnull=False).values_list("embedding", flat=True)
    )
    if not embeddings:
        return

    vectors = np.array(embeddings, dtype=np.float32)
    centroid = np.mean(vectors, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    topic.centroid_embedding = centroid.tolist()
    topic.save(update_fields=["centroid_embedding"])


def cluster_article(article: Article, distance_threshold: float = 0.22, lookback_hours: int = 48) -> Topic:
    """
    Rattache un article à un Topic existant s'il est suffisamment proche
    sémantiquement (< distance_threshold, soit > ~78% de similarité cosinus),
    sinon crée un nouveau Topic.
    """
    if article.embedding is None:
        raise ValueError(f"L'article {article.id} n'a pas d'embedding généré.")

    since = timezone.now() - timedelta(hours=lookback_hours)

    # Recherche du topic le plus proche dans la fenêtre temporelle
    closest_topic = (
        Topic.objects.filter(
            created_at__gte=since,
            centroid_embedding__isnull=False,
        )
        .annotate(distance=CosineDistance("centroid_embedding", article.embedding))
        .filter(distance__lte=distance_threshold)
        .order_by("distance")
        .first()
    )

    if closest_topic:
        # Rattachement au topic existant
        article.topic = closest_topic
        article.save(update_fields=["topic"])
        recalculate_topic_centroid(closest_topic)
        return closest_topic
    else:
        # Création d'un nouveau topic
        new_topic = Topic.objects.create(
            title=article.title,
            category=article.source.category if article.source else "Général",
            centroid_embedding=article.embedding,
        )
        article.topic = new_topic
        article.save(update_fields=["topic"])
        return new_topic
