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

        from .ingestors.twitter import TwitterIngestor
        from .ingestors.instagram import InstagramIngestor

        # Test factory
        self.assertIsInstance(get_ingestor("rss"), RSSIngestor)
        self.assertIsInstance(get_ingestor("reddit"), RedditIngestor)
        self.assertIsInstance(get_ingestor("youtube"), YouTubeIngestor)
        self.assertIsInstance(get_ingestor("twitter"), TwitterIngestor)
        self.assertIsInstance(get_ingestor("instagram"), InstagramIngestor)
        self.assertIsInstance(get_ingestor("inconnu"), RSSIngestor)

        # Test HTML cleaner
        dirty_html = "<div><p>Texte <b>important</b></p><script>alert('hack')</script><style>body {color: red;}</style></div>"
        cleaned = clean_html_text(dirty_html)
        self.assertEqual(cleaned, "Texte important")

    def test_tts_cleaner(self):
        from .services.tts import clean_script_for_tts

        raw = "# Titre\n\nVoici **un résumé** avec un lien https://google.com."
        cleaned = clean_script_for_tts(raw)
        self.assertNotIn("#", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertNotIn("https://", cleaned)
        self.assertIn("un résumé", cleaned)

    def test_telegram_bot_update_handling(self):
        from .services.telegram_bot import handle_telegram_update

        update_payload = {
            "update_id": 99999,
            "message": {
                "message_id": 1,
                "chat": {"id": 888777666, "type": "private"},
                "from": {"id": 888777666, "username": "alex_tech", "first_name": "Alex"},
                "text": "/start",
            },
        }

        handle_telegram_update(update_payload)

        # Vérifier que l'utilisateur et le canal ont été créés
        from django.contrib.auth.models import User
        user = User.objects.get(username="alex_tech")
        self.assertEqual(user.first_name, "Alex")

        channel = DeliveryChannel.objects.get(user=user, channel_type="telegram")
        self.assertEqual(channel.identifier, "888777666")
        self.assertTrue(channel.is_active)

    def test_delivery_dispatcher_fallback(self):
        from .services.delivery import dispatch_digest_to_channels

        # Sans token configuré, le statut doit basculer en 'failed' avec message d'erreur clair
        channel = DeliveryChannel.objects.create(
            user=self.user,
            channel_type="telegram",
            identifier="12345",
        )
        digest = Digest.objects.create(
            user=self.user,
            date=date(2026, 9, 13),
            script_text="Texte du digest test",
        )

        deliveries = dispatch_digest_to_channels(digest)
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].status, "failed")
        self.assertIn("TELEGRAM_BOT_TOKEN", deliveries[0].error_message)

    def test_telegram_conversational_topic_selection(self):
        from .services.telegram_bot import handle_telegram_update
        from django.contrib.auth.models import User

        # Étape 1 : /start
        handle_telegram_update({
            "message": {
                "chat": {"id": 112233},
                "from": {"username": "test_curator", "first_name": "Curator"},
                "text": "/start",
            }
        })
        user = User.objects.get(username="test_curator")
        self.assertEqual(user.preference.conversation_state, "awaiting_scope_choice")

        # Étape 2 : L'utilisateur choisit 1 (Un seul domaine)
        handle_telegram_update({
            "message": {
                "chat": {"id": 112233},
                "from": {"username": "test_curator"},
                "text": "1",
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.conversation_state, "awaiting_single_category")

        # Étape 3 : L'utilisateur choisit 2 (IA)
        handle_telegram_update({
            "message": {
                "chat": {"id": 112233},
                "from": {"username": "test_curator"},
                "text": "2",
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.conversation_state, "")
        self.assertEqual(user.preference.followed_categories, ["IA"])

        # Étape 4 : Reconfiguration multiple via /topics
        handle_telegram_update({
            "message": {
                "chat": {"id": 112233},
                "from": {"username": "test_curator"},
                "text": "/topics",
            }
        })
        handle_telegram_update({
            "message": {
                "chat": {"id": 112233},
                "from": {"username": "test_curator"},
                "text": "2",  # Plusieurs domaines
            }
        })
        handle_telegram_update({
            "message": {
                "chat": {"id": 112233},
                "from": {"username": "test_curator"},
                "text": "1, 2, Cybersécurité",
            }
        })
        user.preference.refresh_from_db()
        self.assertIn("Tech", user.preference.followed_categories)
        self.assertIn("IA", user.preference.followed_categories)
        self.assertIn("Cybersécurité", user.preference.keywords)

    def test_parse_time_string(self):
        from .services.telegram_bot import parse_time_string
        from datetime import time

        self.assertEqual(parse_time_string("07:30"), time(7, 30))
        self.assertEqual(parse_time_string("7h30"), time(7, 30))
        self.assertEqual(parse_time_string("8h"), time(8, 0))
        self.assertEqual(parse_time_string("8"), time(8, 0))
        self.assertIsNone(parse_time_string("25:00"))
        self.assertIsNone(parse_time_string("invalid"))

    def test_telegram_heure_and_fuseau_commands(self):
        from .services.telegram_bot import handle_telegram_update
        from datetime import time

        # /heure directe
        handle_telegram_update({
            "message": {
                "chat": {"id": 445566},
                "from": {"username": "timer_user", "first_name": "Timer"},
                "text": "/heure 08:45",
            }
        })
        user = User.objects.get(username="timer_user")
        self.assertEqual(user.preference.digest_hour, time(8, 45))

        # /fuseau directe
        handle_telegram_update({
            "message": {
                "chat": {"id": 445566},
                "from": {"username": "timer_user"},
                "text": "/fuseau Europe/Paris",
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.timezone, "Europe/Paris")

        # /heure conversationnelle
        handle_telegram_update({
            "message": {
                "chat": {"id": 445566},
                "from": {"username": "timer_user"},
                "text": "/heure",
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.conversation_state, "awaiting_digest_hour")

        handle_telegram_update({
            "message": {
                "chat": {"id": 445566},
                "from": {"username": "timer_user"},
                "text": "06:30",
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.conversation_state, "")
        self.assertEqual(user.preference.digest_hour, time(6, 30))

        # /fuseau conversationnelle par numéro
        handle_telegram_update({
            "message": {
                "chat": {"id": 445566},
                "from": {"username": "timer_user"},
                "text": "/fuseau",
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.conversation_state, "awaiting_timezone")

        handle_telegram_update({
            "message": {
                "chat": {"id": 445566},
                "from": {"username": "timer_user"},
                "text": "1",  # Africa/Douala
            }
        })
        user.preference.refresh_from_db()
        self.assertEqual(user.preference.conversation_state, "")
        self.assertEqual(user.preference.timezone, "Africa/Douala")

    def test_dispatch_scheduled_morning_digests(self):
        from unittest.mock import patch
        from zoneinfo import ZoneInfo
        from .tasks import dispatch_scheduled_morning_digests

        # Configurer l'utilisateur avec l'heure actuelle dans son fuseau
        local_now = datetime.now(ZoneInfo("Africa/Douala"))
        UserPreference.objects.create(
            user=self.user,
            digest_hour=local_now.time(),
            timezone="Africa/Douala",
        )

        with patch("digests.tasks.generate_user_digest_task.delay") as mock_delay:
            result = dispatch_scheduled_morning_digests()
            self.assertIn("1 briefing(s) planifié(s) déclenché(s)", result)
            mock_delay.assert_called_once()

    def test_news_chat_service_and_retrieval(self):
        from unittest.mock import patch, MagicMock
        from .services.news_chat import retrieve_relevant_news, answer_news_question

        dummy_vec = [0.1] * 768
        Article.objects.create(
            source=self.source,
            title="Percée majeure dans les processeurs quantiques",
            url="https://techcrunch.com/quantum-leap-2026",
            raw_content="Des chercheurs ont démontré un avantage quantique commercial.",
            published_at=datetime.now(timezone.utc),
            embedding=dummy_vec,
        )

        with patch("digests.services.news_chat.generate_embedding", return_value=dummy_vec):
            items, context_str = retrieve_relevant_news("quantique")
            self.assertTrue(len(items) > 0)
            self.assertIn("quantique", context_str.lower())

            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "Voici une analyse journalistique sur l'ordinateur quantique [TechCrunch]."
            mock_client.models.generate_content.return_value = mock_response

            with patch("digests.services.news_chat.get_genai_client", return_value=mock_client):
                answer = answer_news_question(self.user, "Explique-moi cette avancée quantique")
                self.assertIn("ordinateur quantique", answer)
                self.assertIn("[TechCrunch]", answer)

    def test_telegram_ask_and_free_text_chat(self):
        from unittest.mock import patch
        from .services.telegram_bot import handle_telegram_update

        # 1. /ask directe
        with patch("digests.services.telegram_bot.answer_news_question_task.delay") as mock_delay:
            handle_telegram_update({
                "message": {
                    "chat": {"id": 778899},
                    "from": {"username": "chat_user", "first_name": "Chatter"},
                    "text": "/ask Quels sont les impacts de l'IA ?",
                }
            })
            mock_delay.assert_called_once()
            args, _ = mock_delay.call_args
            self.assertEqual(args[2], "Quels sont les impacts de l'IA ?")

        # 2. /ask sans argument -> passage à l'état awaiting_news_question
        handle_telegram_update({
            "message": {
                "chat": {"id": 778899},
                "from": {"username": "chat_user"},
                "text": "/ask",
            }
        })
        user = User.objects.get(username="chat_user")
        self.assertEqual(user.preference.conversation_state, "awaiting_news_question")

        # 3. Réponse libre dans l'état awaiting_news_question
        with patch("digests.services.telegram_bot.answer_news_question_task.delay") as mock_delay:
            handle_telegram_update({
                "message": {
                    "chat": {"id": 778899},
                    "from": {"username": "chat_user"},
                    "text": "Peux-tu m'expliquer le projet SWE-2 ?",
                }
            })
            user.preference.refresh_from_db()
            self.assertEqual(user.preference.conversation_state, "")
            mock_delay.assert_called_once()

        # 4. Message texte direct hors commande -> Chat with your news
        with patch("digests.services.telegram_bot.answer_news_question_task.delay") as mock_delay:
            handle_telegram_update({
                "message": {
                    "chat": {"id": 778899},
                    "from": {"username": "chat_user"},
                    "text": "Que s'est-il passé hier avec Bitcoin ?",
                }
            })
            mock_delay.assert_called_once()





