import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Digest, Article, Source, Topic
from .tasks import fetch_all_sources, dispatch_daily_digests
from .services.telegram_bot import handle_telegram_update

logger = logging.getLogger(__name__)


def dashboard(request):
    """
    Page d'accueil et tableau de bord principal avec le dernier podcast audio,
    les statistiques globales et la revue de presse du jour.
    """
    latest_digest = Digest.objects.order_by("-date").first()
    past_digests = Digest.objects.exclude(id=latest_digest.id if latest_digest else -1).order_by("-date")[:5]

    stats = {
        "articles_count": Article.objects.count(),
        "sources_count": Source.objects.filter(is_active=True).count(),
        "topics_count": Topic.objects.count(),
        "breaking_count": Topic.objects.filter(is_breaking_news=True).count(),
    }

    context = {
        "latest_digest": latest_digest,
        "past_digests": past_digests,
        "stats": stats,
    }
    return render(request, "digests/dashboard.html", context)


def digest_detail(request, digest_id):
    """
    Vue détaillée d'une archive de briefing avec écoute audio et analyse par sujet.
    """
    digest = get_object_or_404(Digest, id=digest_id)
    return render(request, "digests/digest_detail.html", {"digest": digest})


def archive_list(request):
    """
    Liste chronologique de tous les briefings archivés.
    """
    digests = Digest.objects.order_by("-date")
    return render(request, "digests/archives.html", {"digests": digests})


def trigger_generation_view(request):
    """
    Bouton web permettant de lancer manuellement une collecte et une synthèse d'actualités.
    """
    if request.method == "POST":
        fetch_all_sources.delay()
        dispatch_daily_digests.delay()
        messages.success(request, "Collecte et génération du briefing lancées en tâche de fond !")
    return redirect("dashboard")


@csrf_exempt
def telegram_webhook(request):
    """
    Endpoint Webhook appelé par Telegram lors de la réception d'un message.
    """
    if request.method != "POST":
        return HttpResponse("Méthode non autorisée", status=405)

    try:
        data = json.loads(request.body.decode("utf-8"))
        handle_telegram_update(data)
        return JsonResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Erreur traitement webhook Telegram: {e}")
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@csrf_exempt
def whatsapp_webhook(request):
    """
    Endpoint Webhook pour la réception des messages WhatsApp (Twilio ou Meta).
    """
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and challenge:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("OK")

    if request.method == "POST":
        content_type = request.content_type or ""
        if "json" in content_type:
            try:
                data = json.loads(request.body.decode("utf-8"))
                logger.info(f"Notification Meta WhatsApp reçue : {data}")
            except Exception as e:
                logger.error(f"Erreur parsing WhatsApp Meta: {e}")
        else:
            from_number = request.POST.get("From")
            body = request.POST.get("Body")
            logger.info(f"Message Twilio WhatsApp reçu de {from_number}: {body}")

        return HttpResponse("OK")

    return HttpResponse("Méthode non autorisée", status=405)
