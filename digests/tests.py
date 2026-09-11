from datetime import date, datetime, timezone
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from .models import Source, Article, Topic, UserPreference, DeliveryChannel, Digest, DigestDelivery


class ModelsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.source = Source.objects.create(
            name="TechCrunch",
            url="https://techcrunch.com/feed/",
            source_type="rss",
            category="Tech",
        )

    def test_create_user_preference_with_format(self):
        pref = UserPreference.objects.create(
            user=self.user,
            format_preference="audio",
            followed_categories=["Tech", "AI"],
            min_importance_score=7,
        )
        self.assertEqual(pref.format_preference, "audio")
        self.assertEqual(self.user.preference.min_importance_score, 7)

    def test_article_unique_url_constraint(self):
        Article.objects.create(
            source=self.source,
            title="Article 1",
            url="https://techcrunch.com/article-1",
            published_at=datetime.now(timezone.utc),
        )
        # Tenter d'insérer le même URL doit lever une IntegrityError
        with self.assertRaises(IntegrityError):
            Article.objects.create(
                source=self.source,
                title="Article 1 Duplicate",
                url="https://techcrunch.com/article-1",
                published_at=datetime.now(timezone.utc),
            )

    def test_digest_unique_user_date_constraint(self):
        d1 = Digest.objects.create(user=self.user, date=date(2026, 9, 11))
        self.assertIsNotNone(d1.id)

        # Même date et même user -> IntegrityError
        with self.assertRaises(IntegrityError):
            Digest.objects.create(user=self.user, date=date(2026, 9, 11))

    def test_delivery_channel_and_digest_delivery(self):
        channel = DeliveryChannel.objects.create(
            user=self.user,
            channel_type="telegram",
            identifier="123456789",
        )
        digest = Digest.objects.create(user=self.user, date=date(2026, 9, 12))
        delivery = DigestDelivery.objects.create(
            digest=digest,
            channel=channel,
            status="pending",
        )
        self.assertEqual(delivery.status, "pending")
        self.assertEqual(delivery.channel.channel_type, "telegram")

    def test_synthesizer_fallback_and_script(self):
        from .services.synthesizer import summarize_topic, generate_digest_script

        topic = Topic.objects.create(title="Nouvelle annonce IA", category="Tech")
        Article.objects.create(
            source=self.source,
            title="Lancement d'un nouveau modèle IA",
            url="https://techcrunch.com/article-ai",
            raw_content="Un nouveau modèle d'IA très puissant a été annoncé.",
            published_at=datetime.now(timezone.utc),
            topic=topic,
        )

        summary = summarize_topic(topic)
        self.assertIn("summary_bullets", summary)
        self.assertTrue(len(summary["summary_bullets"]) > 0)

        script = generate_digest_script([topic], format_preference="both")
        self.assertIn("Nouvelle annonce IA", script)

    def test_ingestor_factory_and_html_cleaner(self):
        from .ingestors import get_ingestor
        from .ingestors.rss import RSSIngestor, clean_html_text
        from .ingestors.reddit import RedditIngestor
        from .ingestors.youtube import YouTubeIngestor

        # Test factory
        self.assertIsInstance(get_ingestor("rss"), RSSIngestor)
        self.assertIsInstance(get_ingestor("reddit"), RedditIngestor)
        self.assertIsInstance(get_ingestor("youtube"), YouTubeIngestor)
        self.assertIsInstance(get_ingestor("inconnu"), RSSIngestor)

        # Test HTML cleaner
        dirty_html = "<div><p>Texte <b>important</b></p><script>alert('hack')</script><style>body {color: red;}</style></div>"
        cleaned = clean_html_text(dirty_html)
        self.assertEqual(cleaned, "Texte important")


