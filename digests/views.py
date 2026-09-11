import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .services.telegram_bot import handle_telegram_update

logger = logging.getLogger(__name__)


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
    # Validation du webhook Meta WhatsApp (GET challenge)
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        if mode == "subscribe" and challenge:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("OK")

    if request.method == "POST":
        # Traitement du message entrant (Twilio envoie en form-data, Meta en JSON)
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

