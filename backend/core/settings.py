import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from root or backend
env_path = BASE_DIR.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key-change-in-production-1234567890')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = ['*'] if DEBUG else [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'vpn.live-dev.by,localhost,127.0.0.1,web').split(',') if h.strip()]

DOMAIN = os.getenv('DOMAIN', 'vpn.live-dev.by')
SITE_URL = os.getenv('SITE_URL', 'http://vpn.live-dev.by')

try:
    import corsheaders
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Custom Apps
    'apps.accounts',
    'apps.billing',
    'apps.vpn',
    'apps.api',
]
if HAS_CORS:
    INSTALLED_APPS.insert(6, 'corsheaders')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.PersistentAuthMiddleware',
    'apps.accounts.middleware.ErrorIncidentMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
if HAS_CORS:
    MIDDLEWARE.insert(0, 'corsheaders.middleware.CorsMiddleware')

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.accounts.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# Database
DB_NAME = os.getenv('DB_NAME', 'vpn_db')
DB_USER = os.getenv('DB_USER', 'vpn_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'vpn_secure_password_123')
DB_HOST = os.getenv('DB_HOST', '')
DB_PORT = os.getenv('DB_PORT', '5432')

if DB_HOST:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
        }
    }
else:
    # Local fallback sqlite for local testing if Postgres container not running
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'accounts.CustomUser'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 6}},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Minsk'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication URLs
LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/auth/login/'

# Email configuration (Password recovery)
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.yandex.ru')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'VPN Live Dev <support@live-dev.by>')

# CORS & CSRF
CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = [
    f'http://{DOMAIN}',
    f'https://{DOMAIN}',
    'http://localhost',
    'http://127.0.0.1',
    'http://localhost:8000',
    'http://localhost:3000',
]

# Allow iframe in Telegram WebApp
X_FRAME_OPTIONS = 'ALLOWALL'
XS_SHARING_ALLOWED_METHODS = ['POST', 'GET', 'OPTIONS', 'PUT', 'DELETE']

# Telegram Bot Config
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'live_vpn_bot')
TELEGRAM_WEBAPP_URL = os.getenv('TELEGRAM_WEBAPP_URL', f'{SITE_URL}/miniapp/')

# bePaid Payment Settings (Belarus / Belkart / ERIP / CIS)
BEPAID_SHOP_ID = os.getenv('BEPAID_SHOP_ID', '4225')
BEPAID_SECRET_KEY = os.getenv('BEPAID_SECRET_KEY', '3834fbef1fe6ea024ef77f5c79ec7ff1ba710ea6241c08c2f341afda8af4c1c4')
BEPAID_TEST_MODE = os.getenv('BEPAID_TEST_MODE', 'True').lower() in ('true', '1')
BEPAID_CHECKOUT_URL = os.getenv('BEPAID_CHECKOUT_URL', 'https://checkout.bepaid.by/ctp/api/checkouts')

# YooKassa Payment Settings (Russia / Self-employed / SBP / MIR / Cards)
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY', '')
YOOKASSA_TEST_MODE = os.getenv('YOOKASSA_TEST_MODE', 'True').lower() in ('true', '1')
YOOKASSA_API_URL = os.getenv('YOOKASSA_API_URL', 'https://api.yookassa.ru/v3/payments')

# ==========================================
# 90-Day Cached Session & Persistent Device Auth
# ==========================================
SESSION_COOKIE_AGE = 90 * 24 * 60 * 60       # 90 days in seconds (7,776,000s)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False     # Keep logged in when browser closes
SESSION_SAVE_EVERY_REQUEST = True           # Rolling 90 days active expiration window
SESSION_COOKIE_HTTPONLY = True              # Prevent XSS extraction
SESSION_COOKIE_NAME = 'vpn_sessionid'
SESSION_COOKIE_SAMESITE = 'Lax'

DEVICE_KEY_COOKIE_NAME = 'vpn_device_key'
DEVICE_KEY_AGE = 90 * 24 * 60 * 60          # 90 days

# ==========================================
# Logging Configuration
# ==========================================
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] {name} ({module}:{lineno}): {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'errors_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'errors.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'level': 'ERROR',
        },
        'vpn_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'vpn.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'level': 'INFO',
        },
        'billing_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'billing.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'level': 'INFO',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console', 'errors_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps.accounts': {
            'handlers': ['console', 'errors_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.vpn': {
            'handlers': ['console', 'vpn_file', 'errors_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.billing': {
            'handlers': ['console', 'billing_file', 'errors_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.api': {
            'handlers': ['console', 'errors_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}



