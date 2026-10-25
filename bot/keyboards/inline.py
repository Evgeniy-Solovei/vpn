from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from urllib.parse import quote
from bot.config import TELEGRAM_WEBAPP_URL, SITE_URL, BOT_USERNAME

def get_main_menu(vpn_data: dict, user_data: dict, devices_data: dict = None, traffic_data: dict = None) -> InlineKeyboardMarkup:
    connect_url = vpn_data.get('connect_url') or f"{SITE_URL}/dashboard/"
    whitelist_active = vpn_data.get('whitelist_enabled', True)
    wl_text = "🛡️ Белый список: ВКЛ" if whitelist_active else "🛡️ Белый список: ВЫКЛ"

    conn_count = devices_data.get('connected_count', 1) if devices_data else 1
    max_dev = devices_data.get('max_devices', 5) if devices_data else 5
    dev_btn_text = f"📱 Устройства: {conn_count}/{max_dev}"

    ref_count = user_data.get('referrals_count', 0)
    ref_btn_text = f"👥 Друзья ({ref_count}) • +3 дн."

    flag = vpn_data.get('flag', '🇫🇷')
    loc_name = vpn_data.get('city') or vpn_data.get('country_name') or 'Франция'
    srv_btn_text = f"🌍 {flag} {loc_name}"

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
                text=dev_btn_text,
                callback_data="view_devices"
            ),
            InlineKeyboardButton(
                text=ref_btn_text,
                callback_data="view_referrals"
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
                text=srv_btn_text,
                callback_data="view_servers"
            ),
            InlineKeyboardButton(
                text=wl_text,
                callback_data="view_whitelist"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Трафик: " + (traffic_data.get('used_display', '0 МБ') if traffic_data else '0 МБ'),
                callback_data="view_traffic"
            ),
            InlineKeyboardButton(
                text="📲 Скачать INCY",
                callback_data="download_app"
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


def get_devices_menu(devices: list = None) -> InlineKeyboardMarkup:
    buttons = []
    if devices:
        for idx, dev in enumerate(devices, 1):
            dev_id = dev.get('id')
            dev_name = dev.get('name') or f"Устройство #{idx}"
            if len(dev_name) > 24:
                dev_name = dev_name[:22] + "…"
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗑️ Удалить #{idx}: {dev_name}",
                    callback_data=f"del_dev_{dev_id}"
                )
            ])

    buttons.append([
        InlineKeyboardButton(text="🗑️ Сбросить все устройства", callback_data="reset_devices")
    ])
    buttons.append([
        InlineKeyboardButton(text="📲 Скачать INCY на новое устройство", callback_data="download_app")
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_referrals_menu(bot_user: str, ref_code: str) -> InlineKeyboardMarkup:
    clean_bot = bot_user or "live_vpn_bot"
    clean_code = ref_code or ""
    bot_link = f"https://t.me/{clean_bot}?start=ref_{clean_code}"
    share_text = quote(f"🚀 Держи быстрый VPN без блокировок и тормозов! Работает YouTube в 4K и банки напрямую. 3 дня бесплатно: {bot_link}")
    share_url = f"https://t.me/share/url?url={quote(bot_link)}&text={share_text}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📲 Поделиться ссылкой с другом", url=share_url)
        ],
        [
            InlineKeyboardButton(text="🚀 Открыть Личный кабинет", web_app=WebAppInfo(url=TELEGRAM_WEBAPP_URL))
        ],
        [
            InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
        ]
    ])


def get_servers_menu(servers: list, current_server_id: int = None) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        s_id = s.get('id')
        flag = s.get('flag', '🌐')
        clean_name = s.get('clean_name', s.get('name', 'Сервер'))
        ping = s.get('ping_ms', 40)
        is_current = (s_id == current_server_id)
        active_mark = " (Активен ✓)" if is_current else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{flag} {clean_name} • {ping} ms{active_mark}",
                callback_data=f"switch_srv_{s_id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_traffic_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ Подключить в 1 клик (INCY)", callback_data="view_key")
        ],
        [
            InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
        ]
    ])


def get_whitelist_menu(whitelist_enabled: bool, custom_domains_count: int, routing_deeplink: str = None) -> InlineKeyboardMarkup:
    ru_by_btn = "🇷🇺 🇧🇾 Режим .ru и .by: 🟢 НАПРЯМУЮ" if whitelist_enabled else "🇷🇺 🇧🇾 Режим .ru и .by: ⚪ ЧЕРЕЗ VPN"
    toggle_btn = "🛡️ Выключить белый список" if whitelist_enabled else "🛡️ Включить белый список"

    buttons = [
        [
            InlineKeyboardButton(text=ru_by_btn, callback_data="toggle_ru_by")
        ],
        [
            InlineKeyboardButton(text="➕ Добавить сайт в исключения", callback_data="add_wl_site")
        ]
    ]
    if routing_deeplink:
        buttons.append([
            InlineKeyboardButton(text="⚡ Включить обход в INCY (ВК, Банки)", url=routing_deeplink)
        ])
    if custom_domains_count > 0:
        buttons.append([
            InlineKeyboardButton(text=f"🗑️ Очистить мои сайты ({custom_domains_count})", callback_data="clear_wl_sites")
        ])
    buttons.append([
        InlineKeyboardButton(text=toggle_btn, callback_data="toggle_whitelist_quick")
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    ])
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


def get_yookassa_tariffs_menu(packages: list = None) -> InlineKeyboardMarkup:
    buttons = []
    if packages:
        for pkg in packages:
            days = pkg.get('days')
            price = pkg.get('price_rub')
            price_int = int(price) if float(price).is_integer() else price
            badge = f" ({pkg['badge']})" if pkg.get('badge') else ""
            buttons.append([
                InlineKeyboardButton(
                    text=f"{days} дн. — {price_int} ₽{badge}",
                    callback_data=f"yoo_pay_{days}_{price_int}"
                )
            ])
    else:
        buttons = [
            [InlineKeyboardButton(text="30 дн. — 105 ₽ (хит)", callback_data="yoo_pay_30_105")],
            [InlineKeyboardButton(text="60 дн. — 200 ₽ (выгодно)", callback_data="yoo_pay_60_200")],
            [InlineKeyboardButton(text="90 дн. — 280 ₽ (максимум)", callback_data="yoo_pay_90_280")],
        ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад к балансу", callback_data="view_balance")])
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


def get_download_menu(connect_url: str = None) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🍏 Для iPhone / iPad (App Store)", url="https://apps.apple.com/app/incy/id6756943388"),
        ],
        [
            InlineKeyboardButton(text="🤖 Для Android (Google Play)", url="https://play.google.com/store/apps/details?id=llc.itdev.incy"),
        ],
        [
            InlineKeyboardButton(text="💻 Для Windows и Mac", url="https://incy.app/skachat/"),
        ],
    ]
    if connect_url:
        buttons.append([
            InlineKeyboardButton(text="⚡ Шаг 2: Подключить в 1 клик", url=connect_url)
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
