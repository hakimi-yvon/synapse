from django.core.management.base import BaseCommand
from digests.models import Source
from digests.tasks import fetch_all_sources, fetch_source


class Command(BaseCommand):
    help = "Déclenche la collecte des articles depuis toutes les sources actives"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Exécute la collecte de manière synchrone sans passer par Celery (idéal pour tester)",
        )

    def handle(self, *args, **options):
        if options["sync"]:
            self.stdout.write("Exécution synchrone de la collecte...\n")
            sources = Source.objects.filter(is_active=True)
            for source in sources:
                self.stdout.write(f"Collecte depuis {source.name} ({source.source_type})...")
                res = fetch_source(source.id)
                self.stdout.write(self.style.SUCCESS(f"-> {res}"))
            self.stdout.write(self.style.SUCCESS("\nCollecte synchrone terminée."))
        else:
            self.stdout.write("Envoi des tâches de collecte dans la file d'attente Celery...")
            task = fetch_all_sources.delay()
            self.stdout.write(self.style.SUCCESS(f"Tâche principale Celery planifiée (Task ID: {task.id})"))
            self.stdout.write("Consultez votre terminal de worker Celery pour voir la collecte en direct !")
