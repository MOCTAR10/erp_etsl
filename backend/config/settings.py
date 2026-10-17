"""
Django settings for the ETSL archiving system.

Configuration is env-driven (see ``backend/.env.example``). Local dev reads
``backend/.env``; production values are injected at deploy time.
"""

import sys
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# ── Security ──
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-only-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

_INSECURE_DEFAULT_KEY = "django-insecure-dev-only-change-me"
if not DEBUG and (SECRET_KEY == _INSECURE_DEFAULT_KEY or len(SECRET_KEY) < 32):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY doit etre defini (>= 32 caracteres) quand DEBUG=False."
    )

# En production derriere le proxy Caddy : cookies securises, HSTS, redirection HTTPS.
# Activable via SECURE_SSL=True (laisse a False pour un deploiement HTTP interne).
SECURE_SSL = env.bool("SECURE_SSL", default=False)
if SECURE_SSL and not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ── Application definition ──
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "users",
    "documents",
    "workflow",
    "reports",
    "referentiels",
    "registres",
    "accounting_kernel",
    "integrations",
    "outbox",
    "commercial",
    "achats",
    "operations",
    "logistique",
    "stocks",
    "qualite",
    "hse",
    "maintenance",
    "rh_paie",
    "comptabilite",
    "controle_gestion",
    "juridique",
    "analytics",
    "django_celery_beat",
    "django_celery_results",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Database (PostgreSQL via Docker Compose) ──
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="etls"),
        "USER": env("POSTGRES_USER", default="etls"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="etls_dev_password"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}

# ── Authentication ──
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ── Django REST Framework ──
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.drf_exception_handler",
    # Protection brute-force / abus : limites par IP (anonyme) et par utilisateur.
    # Desactivees pendant `manage.py test` (les suites enchainent des milliers d'appels).
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": (
        {"anon": "100000/min", "user": "100000/min", "login": "100000/min"}
        if "test" in sys.argv
        else {
            "anon": env("THROTTLE_ANON", default="60/min" if not DEBUG else "100000/min"),
            "user": env("THROTTLE_USER", default="600/min" if not DEBUG else "100000/min"),
            "login": env("THROTTLE_LOGIN", default="10/min" if not DEBUG else "100000/min"),
        }
    ),
}

# ── JWT (RF-55 : email + mot de passe) ──
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ── CORS ──
# RF-81: desktop app only; origins configurable for future web access.
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS", default=[])

# ── Internationalization ──
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Libreville"
USE_I18N = True
USE_TZ = True

# ── Static / media ──
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = env("MEDIA_URL", default="media/")
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# ── MinIO object storage (RF-45 : NAS, S3-compatible) ──
AWS_ACCESS_KEY_ID = env("MINIO_ROOT_USER", default="etls_minio")
AWS_SECRET_ACCESS_KEY = env("MINIO_ROOT_PASSWORD", default="etls_minio_dev_password")
AWS_STORAGE_BUCKET_NAME = "etls-documents"
AWS_S3_ENDPOINT_URL = env("MINIO_ENDPOINT", default="http://localhost:9000")
AWS_S3_ADDRESSING_STYLE = "path"
# URL présignées en SigV4 (SigV2 est déprécié) ; région nominale exigée par la signature (SeaweedFS / S3 compatibles).
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_REGION_NAME = env("S3_REGION", default="us-east-1")
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_S3_FILE_OVERWRITE = False

# Stockage : "s3" (défaut, MinIO/S3) ou "local" (disque serveur, uploads GED).
# "local" évite de dépendre d'un serveur d'objets pour un premier déploiement natif.
STORAGE_BACKEND = env("STORAGE_BACKEND", default="s3")
if STORAGE_BACKEND == "local":
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Celery (relances RF-35, ingestion, OCR, exports programmés) ──
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ── Emails (RF-34 : notifications) — console en dev, SMTP en prod via .env ──
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="archivage@etls.local")

# ── Ingestion (RF-04/05) ──
IMAP_HOST = env("IMAP_HOST", default="")
IMAP_USERNAME = env("IMAP_USERNAME", default="")
IMAP_PASSWORD = env("IMAP_PASSWORD", default="")
IMAP_MAILBOXES = env("IMAP_MAILBOXES", default="INBOX")
WATCHED_FOLDER = env("WATCHED_FOLDER", default="")
