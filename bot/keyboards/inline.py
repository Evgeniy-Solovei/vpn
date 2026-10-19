from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from bot.config import TELEGRAM_WEBAPP_URL, SITE_URL

def get_main_menu(vpn_data: dict, user_data: dict) -> InlineKeyboardMarkup:
    connect_url = vpn_data.get('connect_url') or f"{SITE_URL}/dashboard/"
    whitelist_active = vpn_data.get('whitelist_enabled', True)
    wl_text = "🛡️ Белый список РФ: ВКЛ" if whitelist_active else "🛡️ Белый список РФ: ВЫКЛ"

    buttons = [
        [
            InlineKeyboardButton(
                text="⚡ Подключить в 1 клик (INCY)",
                url=connect_url
            )
        ],
        [
            InlineKeyboardButton(
                text="🚀 Открыть Личный кабинет",
                web_app=WebAppInfo(url=TELEGRAM_WEBAPP_URL)
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Мой VLESS Ключ",
                callback_data="view_key"
            ),
            InlineKeyboardButton(
                text="💳 Баланс и Тарифы",
                callback_data="view_balance"
            )
        ],
        [
            InlineKeyboardButton(
                text=wl_text,
                callback_data="toggle_whitelist"
            ),
            InlineKeyboardButton(
                text="⚡ +50 ГБ Турбо (30 ₽)",
                callback_data="buy_turbo"
            )
        ],
        [
            InlineKeyboardButton(
                text="📲 Скачать INCY",
                callback_data="download_app"
            ),
            InlineKeyboardButton(
                text="👥 Рефералы",
                callback_data="view_referrals"
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Поддержка",
                callback_data="support"
            ),
            InlineKeyboardButton(
                text="🌐 Сайт vpn.live-dev.by",
                url=SITE_URL
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])


def get_download_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍏 iOS (App Store)", url="https://apps.apple.com/app/id6474328827"),
            InlineKeyboardButton(text="🤖 Android (Google Play)", url="https://play.google.com/store")
        ],
        [
            InlineKeyboardButton(text="💻 Windows / macOS", url="https://github.com")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")
        ]
    ])
