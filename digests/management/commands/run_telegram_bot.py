import time
import httpx
from django.conf import settings
from django.core.management.base import BaseCommand
from digests.services.telegram_bot import handle_telegram_update


class Command(BaseCommand):
    help = "Lance le bot Telegram en mode long polling (idéal pour le développement local)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Exécute les tâches de fond en direct de façon synchrone (aucun worker Celery séparé nécessaire)",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            self.stderr.write(self.style.ERROR("Erreur : TELEGRAM_BOT_TOKEN n'est pas configuré dans .env ou settings."))
            return

        if options.get("sync"):
            settings.CELERY_TASK_ALWAYS_EAGER = True
            settings.CELERY_TASK_EAGER_PROPAGATES = True
            self.stdout.write(
                self.style.WARNING("⚡ Mode Synchrone actif (--sync) : les tâches s'exécutent en direct sans worker Celery.")
            )

        self.stdout.write(self.style.SUCCESS("🚀 Bot Telegram Synapse démarré en écoute (Polling)... Appuyez sur Ctrl+C pour arrêter."))

        offset = 0
        url = f"https://api.telegram.org/bot{token}/getUpdates"

        with httpx.Client(timeout=30.0) as client:
            while True:
                try:
                    params = {"offset": offset, "timeout": 20}
                    response = client.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        for update in data.get("result", []):
                            update_id = update["update_id"]
                            offset = update_id + 1
                            self.stdout.write(f"Message reçu (ID {update_id})")
                            handle_telegram_update(update)
                    elif response.status_code == 409:
                        self.stderr.write(self.style.WARNING("Conflit détecté (un webhook est peut-être actif)."))
                        time.sleep(5)
                    else:
                        self.stderr.write(f"Réponse inattendue de Telegram ({response.status_code}): {response.text}")
                        time.sleep(3)
                except KeyboardInterrupt:
                    self.stdout.write(self.style.SUCCESS("\nArrêt du bot Telegram."))
                    break
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Erreur polling: {e}"))
                    time.sleep(3)
