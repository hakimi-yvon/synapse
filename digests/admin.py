from django.contrib import admin
from .models import Source, Article, Topic, UserPreference, DeliveryChannel, Digest, DigestDelivery

admin.site.register(Source)
admin.site.register(Article)
admin.site.register(Topic)
admin.site.register(UserPreference)
admin.site.register(DeliveryChannel)
admin.site.register(Digest)
admin.site.register(DigestDelivery)