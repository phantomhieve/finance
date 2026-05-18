import os

from pftracker.dotenv import load_dotenv

load_dotenv()

bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')
# Single worker on ~1GB shared VMs — each worker is ~100MB+ RSS; concurrency comes from nginx/async.
workers = int(os.environ.get('GUNICORN_WORKERS', '3'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))

max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '1000'))
max_requests_jitter = int(os.environ.get('GUNICORN_MAX_REQUESTS_JITTER', '50'))

accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
