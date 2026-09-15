from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField, HnswIndex


class Source(models.Model):
    name = models.CharField(max_length=200)
    url = models.URLField()
    source_type = models.CharField(
        max_length=20,
        choices=[
            ("rss", "RSS"),
            ("reddit", "Reddit"),
            ("youtube", "YouTube"),
            ("twitter", "Twitter/X"),
            ("instagram", "Instagram"),
            ("api", "API"),
        ],
    )
    category = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Topic(models.Model):
    title = models.CharField(max_length=300)
    summary_bullets = models.JSONField(default=list)
    category = models.CharField(max_length=100)
    importance_score = models.IntegerField(default=5)
    is_breaking_news = models.BooleanField(default=False)
    alert_sent_at = models.DateTimeField(null=True, blank=True, help_text="Date d'envoi de l'alerte breaking news")
    centroid_embedding = VectorField(dimensions=768, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="topic_centroid_hnsw_idx",
                fields=["centroid_embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self):
        return self.title


class Article(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    title = models.CharField(max_length=500)
    url = models.URLField(unique=True)
    raw_content = models.TextField(blank=True)
    embedding = VectorField(dimensions=768, null=True, blank=True)
    published_at = models.DateTimeField()
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            HnswIndex(
                name="article_embed_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self):
        return self.title


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preference")
    format_preference = models.CharField(
        max_length=10,
        choices=[
            ("text", "Texte structuré"),
            ("audio", "Audio uniquement"),
            ("both", "Texte et Audio"),
        ],
        default="both",
    )
    followed_categories = models.JSONField(default=list, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    min_importance_score = models.IntegerField(default=5)
    digest_hour = models.TimeField(default="07:00")
    timezone = models.CharField(max_length=50, default="Africa/Douala", help_text="Fuseau horaire (ex: Africa/Douala, Europe/Paris)")
    receive_breaking_alerts = models.BooleanField(default=True, help_text="Recevoir les alertes d'urgence en temps réel")
    interest_vector = VectorField(dimensions=768, null=True, blank=True, help_text="Profil vectoriel d'intérêt utilisateur")
    conversation_state = models.CharField(max_length=50, default="", blank=True)

    def __str__(self):
        return f"Préférences de {self.user.username}"


class DeliveryChannel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="delivery_channels")
    channel_type = models.CharField(
        max_length=20,
        choices=[("whatsapp", "WhatsApp"), ("telegram", "Telegram"), ("email", "Email"), ("web", "Web")],
    )
    identifier = models.CharField(max_length=200, help_text="Chat ID Telegram, numéro WhatsApp, ou Email")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.channel_type} ({self.identifier})"


class Digest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="digests")
    date = models.DateField()
    topics = models.ManyToManyField(Topic)
    audio_url = models.URLField(null=True, blank=True)
    script_text = models.TextField(blank=True)

    class Meta:
        unique_together = ("user", "date")

    def __str__(self):
        return f"Digest {self.date} pour {self.user.username}"


class DigestDelivery(models.Model):
    digest = models.ForeignKey(Digest, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.ForeignKey(DeliveryChannel, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed")],
        default="pending",
    )
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Envoi {self.digest} via {self.channel.channel_type} [{self.status}]"


class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feedbacks")
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL)
    digest = models.ForeignKey(Digest, null=True, blank=True, on_delete=models.SET_NULL)
    score = models.SmallIntegerField(choices=[(1, "Like"), (-1, "Dislike")])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        sign = "👍" if self.score > 0 else "👎"
        target = f"Topic {self.topic_id}" if self.topic else f"Digest {self.digest_id}"
        return f"Feedback {sign} de {self.user.username} sur {target}"