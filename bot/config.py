import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'vpn_livedev_bot')
WEB_API_URL = os.getenv('WEB_API_URL', 'http://web:8000/api')
SITE_URL = os.getenv('SITE_URL', 'http://vpn.live-dev.by')
TELEGRAM_WEBAPP_URL = os.getenv('TELEGRAM_WEBAPP_URL', f"{SITE_URL}/miniapp/")
