import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'synapse.settings')

app = Celery('synapse')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()    