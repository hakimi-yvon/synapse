from django.core.management.base import BaseCommand
from digests.models import Source


class Command(BaseCommand):
    help = "Ajoute des sources d'actualités par défaut pour tester le système (RSS, Reddit, YouTube)"

    def handle(self, *args, **options):
        sources = [
            {
                "name": "Hacker News",
                "url": "https://hnrss.org/frontpage",
                "source_type": "rss",
                "category": "Tech",
            },
            {
                "name": "TechCrunch",
                "url": "https://techcrunch.com/feed/",
                "source_type": "rss",
                "category": "Startups",
            },
            {
                "name": "Reddit MachineLearning",
                "url": "https://www.reddit.com/r/MachineLearning",
                "source_type": "reddit",
                "category": "IA",
            },
            {
                "name": "Reddit Python",
                "url": "https://www.reddit.com/r/Python",
                "source_type": "reddit",
                "category": "Dev",
            },
            {
                "name": "YouTube Fireship",
                "url": "https://www.youtube.com/@Fireship",
                "source_type": "youtube",
                "category": "Tech",
            },
        ]

        self.stdout.write("Initialisation des sources d'actualités par défaut...")
        for data in sources:
            obj, created = Source.objects.get_or_create(
                url=data["url"],
                defaults={
                    "name": data["name"],
                    "source_type": data["source_type"],
                    "category": data["category"],
                    "is_active": True,
                },
            )
            status = self.style.SUCCESS("créée") if created else self.style.WARNING("déjà existante")
            self.stdout.write(f"• {obj.name} [{obj.source_type}] : {status}")

        self.stdout.write(self.style.SUCCESS("\nToutes les sources sont prêtes !"))
