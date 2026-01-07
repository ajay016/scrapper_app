import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
# Note the double 'p' in scrapper_backend to match your project name
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrapper_backend.settings')

app = Celery('scrapper_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()