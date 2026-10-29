import os
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

# Dev-only fallback; production must set DJANGO_SECRET_KEY in .env
_default_key = 'django-insecure-dev-only-change-me'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', _default_key)

DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')

if not DEBUG and SECRET_KEY == _default_key:
    raise RuntimeError(
        'DJANGO_SECRET_KEY must be set in production. '
        'Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

CSRF_TRUSTED_ORIGINS = os.environ.get(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'http://localhost:8000',
).split(',')

INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',

    # Third party
    'crispy_forms',
    'crispy_bootstrap5',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Local apps
    'tracker',
    'portfolio',
    'jewellery',
    'expenses',
    'mcp_server',
    'oauth2_provider',
    'corsheaders',

    # Must be last — auto-deletes media files on model delete / field replace
    'django_cleanup.apps.CleanupConfig',
]

SITE_ID = 1

_ADMIN_PREFIX = "/vault-manage"

UNFOLD = {
    "SITE_TITLE": "Vault Admin",
    "SITE_HEADER": "Vault",
    "SITE_ICON": lambda request: "/static/favicon.svg",
    "SITE_LOGO": lambda request: "/static/favicon.svg",
    "SITE_FAVICONS": [{"rel": "icon", "sizes": "any", "type": "image/svg+xml", "href": lambda request: "/static/favicon.svg"}],
    "THEME": "dark",
    "COLORS": {
        "primary": {
            "50": "oklch(97% 0.02 265)",
            "100": "oklch(93% 0.04 265)",
            "200": "oklch(87% 0.07 265)",
            "300": "oklch(80% 0.10 265)",
            "400": "oklch(74% 0.13 265)",
            "500": "oklch(68% 0.15 265)",
            "600": "oklch(60% 0.16 265)",
            "700": "oklch(52% 0.15 265)",
            "800": "oklch(43% 0.13 265)",
            "900": "oklch(35% 0.10 265)",
            "950": "oklch(25% 0.07 265)",
        },
    },
    "SIDEBAR": {
        "navigation": [
            {
                "title": "App",
                "items": [
                    {"title": "Back to Vault", "icon": "arrow_back", "link": "/"},
                ],
            },
            {
                "title": "Users & Groups",
                "items": [
                    {"title": "Users", "icon": "people", "link": f"{_ADMIN_PREFIX}/tracker/user/"},
                    {"title": "Account Groups", "icon": "family_restroom", "link": f"{_ADMIN_PREFIX}/tracker/accountgroup/"},
                    {"title": "WebAuthn Credentials", "icon": "fingerprint", "link": f"{_ADMIN_PREFIX}/tracker/webauthncredential/"},
                ],
            },
            {
                "title": "Savings Tracker",
                "items": [
                    {"title": "Transactions", "icon": "receipt_long", "link": f"{_ADMIN_PREFIX}/tracker/transaction/"},
                    {"title": "Categories", "icon": "category", "link": f"{_ADMIN_PREFIX}/tracker/category/"},
                    {"title": "HRA Expenses", "icon": "home_work", "link": f"{_ADMIN_PREFIX}/tracker/hraexpense/"},
                    {"title": "Financial Goals", "icon": "flag", "link": f"{_ADMIN_PREFIX}/tracker/financialgoal/"},
                    {"title": "Goal Increments", "icon": "trending_up", "link": f"{_ADMIN_PREFIX}/tracker/goalincrement/"},
                    {"title": "Goal Adjustments", "icon": "tune", "link": f"{_ADMIN_PREFIX}/tracker/monthlygoaladjustment/"},
                ],
            },
            {
                "title": "Portfolio",
                "items": [
                    {"title": "Zerodha Accounts", "icon": "account_balance", "link": f"{_ADMIN_PREFIX}/portfolio/zerodhaaccount/"},
                    {"title": "Stocks", "icon": "trending_up", "link": f"{_ADMIN_PREFIX}/portfolio/stockholding/"},
                    {"title": "Mutual Funds", "icon": "pie_chart", "link": f"{_ADMIN_PREFIX}/portfolio/mutualfundholding/"},
                    {"title": "EPF Entries", "icon": "savings", "link": f"{_ADMIN_PREFIX}/portfolio/epfentry/"},
                    {"title": "PF Entries", "icon": "savings", "link": f"{_ADMIN_PREFIX}/portfolio/pfentry/"},
                    {"title": "NPS Entries", "icon": "elderly", "link": f"{_ADMIN_PREFIX}/portfolio/npsentry/"},
                    {"title": "Fixed Deposits", "icon": "lock", "link": f"{_ADMIN_PREFIX}/portfolio/fixeddeposit/"},
                    {"title": "Cash", "icon": "payments", "link": f"{_ADMIN_PREFIX}/portfolio/cashposition/"},
                    {"title": "Bonds", "icon": "description", "link": f"{_ADMIN_PREFIX}/portfolio/bondholding/"},
                    {"title": "Crypto", "icon": "currency_bitcoin", "link": f"{_ADMIN_PREFIX}/portfolio/cryptoholding/"},
                    {"title": "Commodities", "icon": "diamond", "link": f"{_ADMIN_PREFIX}/portfolio/commodityholding/"},
                    {"title": "US Stocks (RSU)", "icon": "work", "link": f"{_ADMIN_PREFIX}/portfolio/usstockholding/"},
                    {"title": "Real Estate", "icon": "domain", "link": f"{_ADMIN_PREFIX}/portfolio/realestateholding/"},
                    {"title": "Commodity Prices", "icon": "price_change", "link": f"{_ADMIN_PREFIX}/portfolio/commodityprice/"},
                    {"title": "Snapshots", "icon": "photo_camera", "link": f"{_ADMIN_PREFIX}/portfolio/monthlysnapshot/"},
                    {"title": "Goals", "icon": "target", "link": f"{_ADMIN_PREFIX}/portfolio/financialgoal/"},
                    {"title": "AI Insights", "icon": "psychology", "link": f"{_ADMIN_PREFIX}/portfolio/portfolioinsight/"},
                    {"title": "AI insight cooldown", "icon": "schedule", "link": f"{_ADMIN_PREFIX}/portfolio/insightgenerationsettings/"},
                ],
            },
            {
                "title": "Expenses",
                "items": [
                    {"title": "Expenses", "icon": "receipt", "link": f"{_ADMIN_PREFIX}/expenses/expense/"},
                    {"title": "Categories", "icon": "category", "link": f"{_ADMIN_PREFIX}/expenses/expensecategory/"},
                    {"title": "Merchant Rules", "icon": "rule", "link": f"{_ADMIN_PREFIX}/expenses/merchantrule/"},
                    {"title": "Cards & Accounts", "icon": "credit_card", "link": f"{_ADMIN_PREFIX}/expenses/paymentsource/"},
                    {"title": "Card Statements", "icon": "request_quote", "link": f"{_ADMIN_PREFIX}/expenses/cardstatement/"},
                    {"title": "Gmail Accounts", "icon": "mail", "link": f"{_ADMIN_PREFIX}/expenses/gmailaccount/"},
                ],
            },
            {
                "title": "MCP Server",
                "items": [
                    {"title": "Audit Log", "icon": "history", "link": f"{_ADMIN_PREFIX}/mcp_server/mcpauditlog/"},
                ],
            },
            {
                "title": "OAuth Integrations",
                "items": [
                    {"title": "Applications", "icon": "apps", "link": f"{_ADMIN_PREFIX}/oauth2_provider/application/"},
                    {"title": "Access Tokens", "icon": "key", "link": f"{_ADMIN_PREFIX}/oauth2_provider/accesstoken/"},
                ],
            },
        ],
    },
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'pftracker.urls'

_TEMPLATE_LOADERS = [
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pftracker.context_processors.household_config',
            ],
            'loaders': [('django.template.loaders.cached.Loader', _TEMPLATE_LOADERS)]
            if not DEBUG else _TEMPLATE_LOADERS,
        },
    },
]

WSGI_APPLICATION = 'pftracker.wsgi.wsgi_application'


# Database — uses DATABASE_URL env var if set, otherwise SQLite for local dev
# conn_max_age defaults to 0 to prevent connection exhaustion across ASGI worker threads
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=int(os.environ.get('DJANGO_CONN_MAX_AGE', '0')),
    )
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
        if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# Authentication
AUTH_USER_MODEL = 'tracker.User'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'

AUTHENTICATION_BACKENDS = [
    'allauth.account.auth_backends.AuthenticationBackend',
]

# django-allauth
ACCOUNT_ADAPTER = 'pftracker.adapters.NoSignupAccountAdapter'
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'http' if DEBUG else 'https'
SOCIALACCOUNT_ADAPTER = 'pftracker.adapters.PreExistingEmailAdapter'
SOCIALACCOUNT_LOGIN_ON_GET = False  # login button POSTs with CSRF token (prevents login CSRF)
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_OAUTH_CLIENT_ID', ''),
            'secret': os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', ''),
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Content-Security-Policy: allow inline scripts and Chart.js CDN so dashboard/forms work.
# (If you use Cloudflare and still see CSP blocking, relax or remove CSP in Cloudflare.)
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [
        CSP.SELF,
        CSP.UNSAFE_INLINE,
        CSP.UNSAFE_EVAL,
        "https://cdn.jsdelivr.net",
    ],
    "style-src": [
        CSP.SELF,
        CSP.UNSAFE_INLINE,
        "https://fonts.googleapis.com",
        "https://cdn.jsdelivr.net",
    ],
    "font-src": [CSP.SELF, "https://fonts.gstatic.com"],
    "connect-src": [CSP.SELF, "https://accounts.google.com"],
    "img-src": [CSP.SELF, "data:", "blob:", "https://*.googleusercontent.com"],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.SELF],
}

# WebAuthn (FaceID / biometric unlock)
WEBAUTHN_RP_NAME = os.environ.get('WEBAUTHN_RP_NAME', 'Vault')
WEBAUTHN_ORIGIN = os.environ.get(
    'WEBAUTHN_ORIGIN',
    os.environ.get('VAULT_PUBLIC_URL', 'http://localhost:8000'),
).rstrip('/')
# Must equal (or be a registrable suffix of) the origin's host, or every ceremony fails.
WEBAUTHN_RP_ID = os.environ.get('WEBAUTHN_RP_ID') or urlparse(WEBAUTHN_ORIGIN).hostname or 'localhost'

# Google Sheets / GCS service account JSON (never commit the file)
GOOGLE_SHEETS_CREDENTIALS = os.environ.get(
    'GOOGLE_SHEETS_CREDENTIALS',
    os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', ''),
)

# Security hardening
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Session expiry — 8 hours for a finance app; extend on each request;
# expire when the browser window is closed.
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Cloudflare Tunnel terminates TLS — do NOT redirect internally or it loops
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Logging — emit Django request errors and exceptions to the gunicorn error log
# (stderr / GUNICORN_ERROR_LOG). Without this, 500s produce no traceback anywhere.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # Logs all unhandled request exceptions (the 500 traceback)
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        # Logs database queries at DEBUG level (disable in production if noisy)
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # App-level logger — use logger = logging.getLogger(__name__) in views
        '': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}

# OAuth 2.0 Provider
OAUTH2_PROVIDER = {
    'SCOPES': {'read': 'Read scope', 'write': 'Write scope'},
    'ACCESS_TOKEN_EXPIRE_SECONDS': 36000,
    'PKCE_REQUIRED': True,  # MCP authorization spec mandates PKCE for all clients
    'OAUTH2_VALIDATOR_CLASS': 'mcp_server.oauth.UserBoundGrantValidator',
    'DCR_ENABLED': True,
    'DCR_REGISTRATION_PERMISSION_CLASSES': (
        'mcp_server.oauth.AuthorizationCodeOnlyDCRPermission',
    ),
    'CIMD_ENABLED': True,
}

# CORS Configuration for MCP & OAuth
# Allow CORS for discovery endpoints, MCP API, and OAuth token endpoints
CORS_URLS_REGEX = r'^/(\.well-known/.*|mcp/.*|o/.*)$'
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = (
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
)

# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
VAULT_REPORT_EMAIL = os.environ.get('VAULT_REPORT_EMAIL', EMAIL_HOST_USER)

if not EMAIL_HOST_USER:
    # Fallback to console backend for local development if no email is configured
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# AI & Insights Settings (Vault AI Gateway)
# Providers: 'shakti', 'gemini', or 'auto' (automatic multi-node failover)
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'shakti' if os.environ.get('SHAKTI_API_KEY') else 'gemini')
AI_NODES = os.environ.get('AI_NODES', '')  # Optional structured JSON array of node definitions

# Multi-key & Multi-node pools (comma-separated or single)
SHAKTI_API_KEYS = os.environ.get('SHAKTI_API_KEYS', '')
SHAKTI_API_KEY = os.environ.get('SHAKTI_API_KEY', '')
SHAKTI_BASE_URLS = os.environ.get('SHAKTI_BASE_URLS', '')
SHAKTI_BASE_URL = os.environ.get('SHAKTI_BASE_URL', 'https://http.prod-llm.shaktistudio.shakticloud.ai')
SHAKTI_CLIENT_ID = os.environ.get('SHAKTI_CLIENT_ID', '')
SHAKTI_MODEL = os.environ.get('SHAKTI_MODEL', 'deepseek-r1')
SHAKTI_MAX_TOKENS = int(os.environ.get('SHAKTI_MAX_TOKENS', '8192'))
SHAKTI_TIMEOUT = float(os.environ.get('SHAKTI_TIMEOUT', '300.0'))
SHAKTI_TEMPERATURE = float(os.environ.get('SHAKTI_TEMPERATURE', '0.1'))
SHAKTI_MAX_RETRIES = int(os.environ.get('SHAKTI_MAX_RETRIES', '3'))
SHAKTI_RETRY_DELAY = int(os.environ.get('SHAKTI_RETRY_DELAY', '3'))

GEMINI_API_KEYS = os.environ.get('GEMINI_API_KEYS', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-4-argon')
EXPENSES_GEMINI_MODEL = os.environ.get('EXPENSES_GEMINI_MODEL', 'gemini-3.8-flash')

# Multi-Stage DAG Engine for Portfolio Insights
ENABLE_PORTFOLIO_DAG = os.environ.get('ENABLE_PORTFOLIO_DAG', 'true').lower() in ('true', '1', 'yes')
PORTFOLIO_DAG_CONCURRENCY = os.environ.get('PORTFOLIO_DAG_CONCURRENCY', 'true').lower() in ('true', '1', 'yes')


