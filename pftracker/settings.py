import os
from pathlib import Path

import dj_database_url
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

_default_key = 'django-insecure-3$+o@5+q0$7*wk&k9e*73*91=eu+rh9(*jh7=1a5id5h#u^&5a'
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
                    {"title": "NPS Entries", "icon": "elderly", "link": f"{_ADMIN_PREFIX}/portfolio/npsentry/"},
                    {"title": "Fixed Deposits", "icon": "lock", "link": f"{_ADMIN_PREFIX}/portfolio/fixeddeposit/"},
                    {"title": "Cash", "icon": "payments", "link": f"{_ADMIN_PREFIX}/portfolio/cashposition/"},
                    {"title": "Bonds", "icon": "description", "link": f"{_ADMIN_PREFIX}/portfolio/bondholding/"},
                    {"title": "Crypto", "icon": "currency_bitcoin", "link": f"{_ADMIN_PREFIX}/portfolio/cryptoholding/"},
                    {"title": "Commodities", "icon": "diamond", "link": f"{_ADMIN_PREFIX}/portfolio/commodityholding/"},
                    {"title": "US Stocks (RSU)", "icon": "work", "link": f"{_ADMIN_PREFIX}/portfolio/usstockholding/"},
                    {"title": "Commodity Prices", "icon": "price_change", "link": f"{_ADMIN_PREFIX}/portfolio/commodityprice/"},
                    {"title": "Snapshots", "icon": "photo_camera", "link": f"{_ADMIN_PREFIX}/portfolio/monthlysnapshot/"},
                    {"title": "Goals", "icon": "target", "link": f"{_ADMIN_PREFIX}/portfolio/financialgoal/"},
                    {"title": "AI Insights", "icon": "psychology", "link": f"{_ADMIN_PREFIX}/portfolio/portfolioinsight/"},
                    {"title": "AI insight cooldown", "icon": "schedule", "link": f"{_ADMIN_PREFIX}/portfolio/insightgenerationsettings/"},
                ],
            },
        ],
    },
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
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
            ],
            'loaders': [('django.template.loaders.cached.Loader', _TEMPLATE_LOADERS)]
            if not DEBUG else _TEMPLATE_LOADERS,
        },
    },
]

WSGI_APPLICATION = 'pftracker.wsgi.application'


# Database — uses DATABASE_URL env var if set, otherwise SQLite for local dev
# conn_max_age: persistent connections for Postgres (reduces connect overhead; tune if max_connections is low)
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
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

STORAGES = {
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
SOCIALACCOUNT_LOGIN_ON_GET = True
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
    "img-src": [CSP.SELF, "data:", "https://*.googleusercontent.com"],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.SELF],
}

# WebAuthn (FaceID / biometric unlock)
WEBAUTHN_RP_ID = os.environ.get('WEBAUTHN_RP_ID', 'localhost')
WEBAUTHN_RP_NAME = 'Vault'
WEBAUTHN_ORIGIN = os.environ.get(
    'WEBAUTHN_ORIGIN',
    'http://localhost:8000' if DEBUG else 'https://finance.phantomhive.in',
)

# Security hardening
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

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
