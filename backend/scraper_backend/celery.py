import os
from celery import Celery

# Use the ONE 'p' spelling to match your folder
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scraper_backend.settings')

app = Celery('scraper_backend')

# Namespace='CELERY' means all celery-related configs 
# in settings.py must start with CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Look for task.py files in your 'api' and 'parser' apps
app.autodiscover_tasks()