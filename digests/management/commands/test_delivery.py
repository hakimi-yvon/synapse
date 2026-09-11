from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from digests.models import DeliveryChannel, Digest, Topic
from digests.services.delivery.dispatcher import dispatch_digest_to_channels
from datetime import date


class Command(BaseCommand):
    help = "Envoie un briefing de test directement sur WhatsApp ou Telegram"

    def add_arguments(self, parser):
        parser.add_argument("--channel", choices=["whatsapp", "telegram"], required=True, help="Type de canal (whatsapp ou telegram)")
        parser.add_argument("--to", required=True, help="Numéro de téléphone (ex: +33612345678) ou Chat ID Telegram")
        parser.add_argument("--username", default="admin", help="Nom de l'utilisateur Django associé")

    def handle(self, *args, **options):
        channel_type = options["channel"]
        recipient = options["to"].strip()
        username = options["username"]

        self.stdout.write(f"Test d'envoi vers {channel_type.upper()} ({recipient})...")

        # Trouver ou créer l'utilisateur
        user, _ = User.objects.get_or_create(username=username)

        # Enregistrer ou mettre à jour le canal de diffusion
        channel, _ = DeliveryChannel.objects.update_or_create(
            user=user,
            channel_type=channel_type,
            defaults={"identifier": recipient, "is_active": True},
        )

        # Créer un digest factice de test
        test_text = (
            "🚀 *Test de diffusion Synapse réussi !*\n\n"
            "Ceci est un message de test envoyé depuis votre plateforme Synapse.\n"
            "• *Sujet 1* : Collecte multi-sources opérationnelle.\n"
            "• *Sujet 2* : Synthèse IA et diffusion validées.\n\n"
            "Votre canal est correctement connecté !"
        )

        digest, _ = Digest.objects.update_or_create(
            user=user,
            date=date.today(),
            defaults={"script_text": test_text},
        )

        # Lancer la diffusion
        deliveries = dispatch_digest_to_channels(digest)

        for d in deliveries:
            if d.channel.channel_type == channel_type:
                if d.status == "sent":
                    self.stdout.write(self.style.SUCCESS(f"✅ Message envoyé avec succès sur {channel_type.upper()} !"))
                else:
                    self.stdout.write(self.style.ERROR(f"❌ Échec de l'envoi : {d.error_message}"))
