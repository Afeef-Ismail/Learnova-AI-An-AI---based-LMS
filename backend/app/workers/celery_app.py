import os
from celery import Celery

broker_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672//")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "rpc://")

celery_app = Celery("learnova", broker=broker_url, backend=result_backend)

# Autodiscover tasks from the workers package
celery_app.autodiscover_tasks(["app.workers"]) 

@celery_app.task(name="health.ping")
def ping():
    return "pong"
