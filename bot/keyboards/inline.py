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
                text="🌍 Сменить локацию",
                web_app=WebAppInfo(url=f"{TELEGRAM_WEBAPP_URL}#servers")
            )
        ],
        [
            InlineKeyboardButton(
                text="📲 Скачать приложение",
                callback_data="download_app"
            ),
            InlineKeyboardButton(
                text="👥 Рефералы",
                callback_data="view_referrals"
            )
        ],
        [
            InlineKeyboardButton(
                text="💻 Войти на сайте (ПК)",
                callback_data="web_magic_login"
            ),
            InlineKeyboardButton(
                text="💬 Поддержка",
                callback_data="support"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])


def get_balance_menu() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="🇷🇺 Пополнить через ЮKassa (СБП / МИР)",
                callback_data="pay_yookassa"
            )
        ],
        [
            InlineKeyboardButton(
                text="🇧🇾 Пополнить через bePaid (РБ / ЕРИП)",
                callback_data="pay_bepaid"
            )
        ],
        [
            InlineKeyboardButton(
                text="🚀 Открыть Личный кабинет",
                web_app=WebAppInfo(url=TELEGRAM_WEBAPP_URL)
            )
        ],
        [
            InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_yookassa_tariffs_menu() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="30 дн. — 105 ₽ (3.50 ₽/день)", callback_data="yoo_pay_105")
        ],
        [
            InlineKeyboardButton(text="60 дн. — 200 ₽ (выгодно)", callback_data="yoo_pay_200")
        ],
        [
            InlineKeyboardButton(text="90 дн. — 280 ₽ (хит)", callback_data="yoo_pay_280")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад к балансу", callback_data="view_balance")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_yookassa_pay_button(checkout_url: str, amount: int, days: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"💳 Оплатить {amount} ₽ в ЮKassa",
                url=checkout_url
            )
        ],
        [
            InlineKeyboardButton(text="◀️ К тарифам", callback_data="pay_yookassa"),
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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
