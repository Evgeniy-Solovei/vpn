import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'vpn_livedev_bot')
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000')
WEB_API_URL = os.getenv('WEB_API_URL', f"{SITE_URL}/api")
TELEGRAM_WEBAPP_URL = os.getenv('TELEGRAM_WEBAPP_URL', f"{SITE_URL}/miniapp/")
