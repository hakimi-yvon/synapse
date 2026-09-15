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

    def test_dispatch_breaking_news_alert_task(self):
        from unittest.mock import patch
        from .tasks import dispatch_breaking_news_alert_task

        topic = Topic.objects.create(
            title="Alerte Séisme Majeur et Tsunami",
            summary_bullets=["Magnitude 8.2 enregistrée", "Alerte côtière déclenchée", "Évacuations en cours"],
            category="Général",
            importance_score=10,
            is_breaking_news=True,
        )

        channel = DeliveryChannel.objects.create(
            user=self.user,
            channel_type="telegram",
            identifier="999888",
        )
        self.user.preference.receive_breaking_alerts = True
        self.user.preference.save()

        with patch("digests.services.telegram_bot.send_telegram_reply", return_value=True) as mock_send:
            res = dispatch_breaking_news_alert_task(topic.id)
            self.assertIn("1 canaux notifiés", res)
            mock_send.assert_called_once()

            topic.refresh_from_db()
            self.assertIsNotNone(topic.alert_sent_at)

            # Deuxième appel -> idempotent, pas de renvoi
            res2 = dispatch_breaking_news_alert_task(topic.id)
            self.assertIn("Alerte déjà envoyée", res2)

    def test_telegram_alertes_command(self):
        from .services.telegram_bot import handle_telegram_update

        # Désactiver
        handle_telegram_update({
            "message": {
                "chat": {"id": 554433},
                "from": {"username": "alert_tester", "first_name": "AlertTester"},
                "text": "/alertes off",
            }
        })
        user = User.objects.get(username="alert_tester")
        self.assertFalse(user.preference.receive_breaking_alerts)

        # Réactiver
        handle_telegram_update({
            "message": {
                "chat": {"id": 554433},
                "from": {"username": "alert_tester"},
                "text": "/alertes on",
            }
        })
        user.preference.refresh_from_db()
        self.assertTrue(user.preference.receive_breaking_alerts)

    def test_process_user_feedback_and_vector_update(self):
        from .services.recommendation import process_user_feedback

        dummy_vec = [0.2] * 768
        topic = Topic.objects.create(
            title="Sujet Apprécié",
            category="Tech",
            centroid_embedding=dummy_vec,
        )

        success, msg = process_user_feedback(self.user, score=1, topic_id=topic.id)
        self.assertTrue(success)
        self.assertIn("Merci", msg)

        self.user.preference.refresh_from_db()
        self.assertIsNotNone(self.user.preference.interest_vector)
        self.assertEqual(len(self.user.preference.interest_vector), 768)

        # Dislike
        success2, msg2 = process_user_feedback(self.user, score=-1, topic_id=topic.id)
        self.assertTrue(success2)
        self.assertIn("noté", msg2)

    def test_telegram_feedback_callback_and_commands(self):
        from .services.telegram_bot import handle_telegram_update

        digest = Digest.objects.create(user=self.user, date=date(2026, 9, 14))

        # Callback query 👍
        handle_telegram_update({
            "callback_query": {
                "id": "cb_12345",
                "from": {"id": 11223344, "username": self.user.username},
                "data": f"fb:dig:{digest.id}:1",
                "message": {"message_id": 99, "chat": {"id": 11223344}},
            }
        })

        self.assertTrue(self.user.feedbacks.filter(digest=digest, score=1).exists())

        # Commande /like
        handle_telegram_update({
            "message": {
                "chat": {"id": 11223344},
                "from": {"username": self.user.username},
                "text": "/like",
            }
        })
        self.assertEqual(self.user.feedbacks.count(), 2)

    def test_dashboard_and_archive_views(self):
        from django.test import RequestFactory
        from digests.views import dashboard, archive_list, digest_detail, trigger_generation_view
        from unittest.mock import patch

        factory = RequestFactory()
        digest = Digest.objects.create(
            user=self.user,
            date=date(2026, 9, 15),
            script_text="Revue de presse générale du jour.",
            audio_url="/media/audio/digests/digest_test.mp3",
        )

        # 1. Dashboard view
        req = factory.get("/")
        res = dashboard(req)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Tableau de Bord Synapse", res.content)

        # 2. Archive list view
        req2 = factory.get("/archives/")
        res2 = archive_list(req2)
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b"Archives des Briefings", res2.content)

        # 3. Digest detail view
        req3 = factory.get(f"/digest/{digest.id}/")
        res3 = digest_detail(req3, digest_id=digest.id)
        self.assertEqual(res3.status_code, 200)
        self.assertIn(b"Revue de presse", res3.content)

        # 4. Trigger generation view
        with patch("digests.views.fetch_all_sources.delay") as mock_fetch, \
             patch("digests.views.dispatch_daily_digests.delay") as mock_dispatch:
            req4 = factory.post("/generate/")
            from django.contrib.messages.storage.fallback import FallbackStorage
            setattr(req4, "session", {})
            setattr(req4, "_messages", FallbackStorage(req4))
            res4 = trigger_generation_view(req4)
            self.assertEqual(res4.status_code, 302)
            mock_fetch.assert_called_once()
            mock_dispatch.assert_called_once()





