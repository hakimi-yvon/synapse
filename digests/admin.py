from django.contrib import admin
from .models import Source, Article, Topic, UserPreference, DeliveryChannel, Digest, DigestDelivery


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "category", "is_active", "last_fetched_at")
    list_filter = ("source_type", "category", "is_active")
    search_fields = ("name", "url")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "published_at", "topic")
    list_filter = ("source", "published_at")
    search_fields = ("title", "raw_content", "url")
    readonly_fields = ("published_at",)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "importance_score", "is_breaking_news", "created_at")
    list_filter = ("category", "is_breaking_news", "created_at")
    search_fields = ("title",)


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "format_preference", "min_importance_score", "digest_hour")
    list_filter = ("format_preference", "digest_hour")


@admin.register(DeliveryChannel)
class DeliveryChannelAdmin(admin.ModelAdmin):
    list_display = ("user", "channel_type", "identifier", "is_active")
    list_filter = ("channel_type", "is_active")
    search_fields = ("identifier", "user__username")


class DigestDeliveryInline(admin.TabularInline):
    model = DigestDelivery
    extra = 0
    readonly_fields = ("channel", "status", "sent_at", "error_message")


@admin.register(Digest)
class DigestAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "audio_url")
    list_filter = ("date",)
    search_fields = ("user__username", "script_text")
    inlines = [DigestDeliveryInline]


@admin.register(DigestDelivery)
class DigestDeliveryAdmin(admin.ModelAdmin):
    list_display = ("digest", "channel", "status", "sent_at")
    list_filter = ("status", "channel__channel_type", "sent_at")
    readonly_fields = ("sent_at",)