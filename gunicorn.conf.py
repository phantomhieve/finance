bind = '127.0.0.1:8000'
# Single worker on ~1GB shared VMs — each worker is ~100MB+ RSS; concurrency comes from nginx/async.
workers = 3
timeout = 120
keepalive = 5

max_requests = 1000
max_requests_jitter = 50

accesslog = '/var/log/vault/gunicorn-access.log'
errorlog = '/var/log/vault/gunicorn-error.log'
loglevel = 'info'
