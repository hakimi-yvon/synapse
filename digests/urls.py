from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("archives/", views.archive_list, name="archives"),
    path("digest/<int:digest_id>/", views.digest_detail, name="digest_detail"),
    path("generate/", views.trigger_generation_view, name="trigger_generation"),
    path("webhook/telegram/", views.telegram_webhook, name="telegram_webhook"),
    path("webhook/whatsapp/", views.whatsapp_webhook, name="whatsapp_webhook"),
]
