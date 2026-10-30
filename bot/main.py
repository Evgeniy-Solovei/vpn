import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN, WEB_API_URL, SITE_URL, SUPPORT_TELEGRAM, BOT_USERNAME
from bot.keyboards.inline import (
    get_main_menu,
    get_back_menu,
    get_download_menu,
    get_balance_menu,
    get_yookassa_tariffs_menu,
    get_yookassa_pay_button,
    get_devices_menu,
    get_referrals_menu,
    get_servers_menu,
    get_traffic_menu,
    get_whitelist_menu,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


async def sync_user_with_backend(telegram_id: int, username: str = None, ref_code: str = None) -> dict:
    """Sync or register user with backend and get VPN credentials."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            payload = {
                "telegram_id": str(telegram_id),
                "telegram_username": username or "",
                "ref_code": ref_code
            }
            resp = await client.post(f"{WEB_API_URL}/tg/sync/", json=payload)
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"Sync failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Error calling backend API: {e}")
    return {}


@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    telegram_id = message.from_user.id
    username = message.from_user.username
    raw_arg = command.args if command.args else None

    # Handle Web Account Linking with +2 days bonus
    if raw_arg and raw_arg.startswith('link_'):
        link_code = raw_arg[5:].strip()
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{WEB_API_URL}/tg/link-account/",
                    json={
                        "code": link_code,
                        "telegram_id": str(telegram_id),
                        "telegram_username": username or ""
                    }
                )
                res_data = resp.json()
                if res_data.get('success'):
                    data = await sync_user_with_backend(telegram_id, username)
                    user_info = data.get('user', {})
                    vpn_info = data.get('vpn', {})
                    bonus_text = "\n🎁 <b>Вам начислено +2 дня бесплатного VPN!</b> (всего 3 дня)\n" if res_data.get('bonus_awarded') else ""
                    msg_text = (
                        f"🎉 <b>Telegram успешно привязан к аккаунту {res_data.get('username')}!</b>\n"
                        f"{bonus_text}\n"
                        f"💰 Ваш текущий баланс: <b>{res_data.get('new_balance')} ₽</b> (на {res_data.get('days_left')} дн.)\n\n"
                        f"⚡ Теперь ваш аккаунт на сайте и в Telegram полностью синхронизированы. Ключи и настройки едины!"
                    )
                    await message.answer(msg_text, parse_mode="HTML", reply_markup=get_main_menu(vpn_info, user_info))
                    return
                else:
                    err_msg = res_data.get('error', 'Не удалось привязать аккаунт')
                    await message.answer(f"⚠️ <b>Ошибка привязки:</b> {err_msg}", parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error linking account: {e}")
                await message.answer("⚠️ Ошибка соединения с сервером при привязке аккаунта.", parse_mode="HTML")

    # Handle One-Click Web Login Deep Link
    if raw_arg == 'login':
        await sync_user_with_backend(telegram_id, username)
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{WEB_API_URL}/tg/generate-magic-link/",
                    json={"telegram_id": str(telegram_id)}
                )
                res_data = resp.json()
                if res_data.get('success'):
                    login_url = res_data.get('login_url')
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🚀 Войти в личный кабинет на сайте", url=login_url)]
                    ])
                    await message.answer(
                        f"💻 <b>Вход в личный кабинет VPN live-dev</b>\n\n"
                        f"Нажмите кнопку ниже, чтобы мгновенно войти в кабинет на компьютере без пароля:\n\n"
                        f"👉 <a href=\"{login_url}\"><b>Войти в личный кабинет &rarr;</b></a>\n\n"
                        f"⏳ <i>Ссылка защищена и действует 15 минут.</i>",
                        parse_mode="HTML",
                        reply_markup=kb,
                        disable_web_page_preview=True
                    )
                    return
            except Exception as e:
                logger.error(f"Error login deep link: {e}")

    ref_code = raw_arg if raw_arg and not raw_arg.startswith('link_') and raw_arg != 'login' else None

    data = await sync_user_with_backend(telegram_id, username, ref_code)
    user_info = data.get('user', {})
    vpn_info = data.get('vpn', {})
    traffic_info = data.get('traffic', {})

    server_title = vpn_info.get('server_name') or '🇫🇷 Франция • Париж'
    ping_ms = vpn_info.get('ping_ms', 38)
    used_display = traffic_info.get('used_display', '0.0 МБ')
    limit_gb = traffic_info.get('limit_gb') or 150
    traffic_line = f"• Трафик: <b>{used_display} / {limit_gb} ГБ</b> (квота на месяц)"

    devices_info = data.get('devices', {})
    conn_count = devices_info.get('connected_count', 1)
    max_dev = devices_info.get('max_devices', 5)

    welcome_text = (
        f"👋 <b>Добро пожаловать в VPN live-dev!</b>\n\n"
        f"⚡ <b>Быстрый и защищенный VPN без блокировок для РФ и РБ.</b>\n"
        f"• Протокол: <b>VLESS Reality</b> (маскировка под чистый трафик)\n"
        f"• Сервер: <b>{server_title}</b> (Пинг: {ping_ms} ms)\n"
        f"• Скорость: <b>1 Gbps • Безлимит</b>\n"
        f"{traffic_line}\n"
        f"• Устройства: <b>{conn_count} из {max_dev} онлайн</b> 📱 (iOS, Android, ПК, ТВ)\n"
        f"• Белый список РФ: <b>{'ВКЛ (банки напрямую)' if vpn_info.get('whitelist_enabled') else 'ВЫКЛ'}</b>\n\n"
        f"💰 Ваш баланс: <b>{user_info.get('balance', 15.0)} ₽</b> (хватит на {user_info.get('days_left', 3)} дн.)\n"
        f"👥 Приглашено друзей: <b>{user_info.get('referrals_count', 0)}</b> (+3 дня за друга)\n\n"
        f"👇 <i>Нажмите «Подключить в 1 клик» для моментальной настройки приложения INCY:</i>"
    )

    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu(vpn_info, user_info, devices_info, traffic_info)
    )


@dp.message(Command("link"))
async def cmd_link(message: Message, command: CommandObject):
    telegram_id = message.from_user.id
    username = message.from_user.username
    link_code = (command.args or "").strip()

    if not link_code:
        await message.answer(
            "ℹ️ <b>Привязка Telegram к сайту</b>\n\n"
            "Чтобы привязать Telegram и получить <b>+2 дня бесплатно</b>:\n"
            "1. В личном кабинете на сайте нажмите кнопку <b>«⚡ Забрать +2 дня в Telegram»</b>\n"
            "2. Или скопируйте 16-значный код и отправьте:\n"
            "<code>/link ВАШ_КОД</code>",
            parse_mode="HTML"
        )
        return

    if link_code.startswith("link_"):
        link_code = link_code[5:].strip()

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/tg/link-account/",
                json={
                    "code": link_code,
                    "telegram_id": str(telegram_id),
                    "telegram_username": username or ""
                }
            )
            res_data = resp.json()
            if res_data.get('success'):
                data = await sync_user_with_backend(telegram_id, username)
                user_info = data.get('user', {})
                vpn_info = data.get('vpn', {})
                bonus_text = "\n🎁 <b>Вам начислено +2 дня бесплатного VPN!</b>\n" if res_data.get('bonus_awarded') else ""
                msg_text = (
                    f"🎉 <b>Telegram успешно привязан и объединен с аккаунтом {res_data.get('username')}!</b>\n"
                    f"{bonus_text}\n"
                    f"💰 Ваш единый баланс: <b>{res_data.get('new_balance')} ₽</b> (на {res_data.get('days_left')} дн.)\n\n"
                    f"⚡ <b>Все данные объединены:</b> вход на сайте (по логину/паролю, Google или в 1 клик) и бот теперь работают как единое целое!"
                )
                await message.answer(msg_text, parse_mode="HTML", reply_markup=get_main_menu(vpn_info, user_info))
            else:
                err_msg = res_data.get('error', 'Не удалось привязать аккаунт')
                await message.answer(f"⚠️ <b>Ошибка привязки:</b> {err_msg}", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in cmd_link: {e}")
            await message.answer("⚠️ Ошибка соединения с сервером при привязке аккаунта.", parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    user_info = data.get('user', {})
    vpn_info = data.get('vpn', {})
    traffic_info = data.get('traffic', {})
    devices_info = data.get('devices', {})

    server_title = vpn_info.get('server_name') or '🇫🇷 Франция • Париж'
    ping_ms = vpn_info.get('ping_ms', 38)
    used_display = traffic_info.get('used_display', '0.0 МБ')
    limit_gb = traffic_info.get('limit_gb') or 150
    traffic_line = f"• Трафик: <b>{used_display} / {limit_gb} ГБ</b> (квота на месяц)"

    conn_count = devices_info.get('connected_count', 1)
    max_dev = devices_info.get('max_devices', 5)

    text = (
        f"🏠 <b>Главное меню VPN live-dev</b>\n\n"
        f"• Баланс: <b>{user_info.get('balance', 0)} ₽</b> (на {user_info.get('days_left', 0)} дн.)\n"
        f"• Сервер: <b>{server_title}</b> ({ping_ms} ms)\n"
        f"• Скорость: <b>1 Gbps • Безлимит</b>\n"
        f"{traffic_line}\n"
        f"• Устройства: <b>{conn_count} из {max_dev} онлайн</b> 📱\n"
        f"• Рефералы: <b>{user_info.get('referrals_count', 0)} друзей</b> (+3 дня за друга)\n"
        f"• Белый список РФ: {'<b>ВКЛ (банки напрямую)</b>' if vpn_info.get('whitelist_enabled') else '<b>ВЫКЛ (весь трафик в VPN)</b>'}"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu(vpn_info, user_info, devices_info, traffic_info))
    await call.answer()


@dp.callback_query(F.data == "view_key")
async def cb_view_key(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    vpn_info = data.get('vpn', {})
    vless_url = vpn_info.get('vless_url', '')
    sub_url = vpn_info.get('sub_url', '')
    max_dev = vpn_info.get('max_devices', 5)

    text = (
        f"🔑 <b>Ваш доступ к VPN</b>\n\n"
        f"💡 <b>Всего 2 простых шага (30 секунд):</b>\n"
        f"1️⃣ <b>Шаг 1:</b> Скачайте бесплатное приложение <b>INCY</b>\n"
        f"2️⃣ <b>Шаг 2:</b> Нажмите <b>«⚡ Подключить в 1 клик»</b> — всё настроится автоматически!\n\n"
        f"<i>В приложении просто нажмите круглую кнопку «Подключить». Больше ничего настраивать не нужно.</i>\n\n"
        f"───────────────\n"
        f"📋 <b>Для ручной вставки (если нужно):</b>\n"
        f"<code>{vless_url}</code>\n\n"
        f"📱 <i>Лимит: до {max_dev} устройств одновременно (телефон, ПК, Smart TV).</i>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Подключить в 1 клик (INCY)", url=vpn_info.get('connect_url') or f"{SITE_URL}/dashboard/")],
        [InlineKeyboardButton(text="📲 Скачать приложение INCY", callback_data="download_app")],
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    await call.answer()


@dp.callback_query(F.data == "view_balance")
async def cb_view_balance(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    user_info = data.get('user', {})

    text = (
        f"💳 <b>Состояние баланса:</b>\n\n"
        f"• Текущий баланс: <b>{user_info.get('balance', 0)} ₽</b>\n"
        f"• Ежедневный тариф: <b>{user_info.get('daily_deduction', 3.50)} ₽ / сутки</b>\n"
        f"• Оплачено дней: <b>{user_info.get('days_left', 0)} дней</b>\n\n"
        f"👇 Выберите способ пополнения баланса:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_balance_menu(), disable_web_page_preview=True)
    await call.answer()


@dp.callback_query(F.data == "pay_yookassa")
async def cb_pay_yookassa(call: CallbackQuery):
    packages = []
    async with httpx.AsyncClient(timeout=6.0) as client:
        try:
            resp = await client.get(f"{WEB_API_URL}/billing/tariffs/")
            if resp.status_code == 200:
                packages = resp.json().get('packages', [])
        except Exception as e:
            logger.debug(f"Error fetching packages: {e}")

    text = (
        f"🇷🇺 <b>Оплата через ЮKassa (РФ):</b>\n\n"
        f"• Моментальное зачисление через <b>СБП (0%)</b>, карты МИР, Сбер, Т-Банк\n"
        f"• Официальный фискальный чек для самозанятых (НПД)\n\n"
        f"Выберите период подписки:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_yookassa_tariffs_menu(packages))
    await call.answer()


@dp.callback_query(F.data.startswith("yoo_pay_"))
async def cb_yoo_pay_amount(call: CallbackQuery):
    # Support both yoo_pay_{days}_{amount} and legacy yoo_pay_{amount}
    raw = call.data.replace("yoo_pay_", "")
    parts = raw.split("_")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        days = int(parts[0])
        amount = int(parts[1])
    else:
        amount_map = {
            "105": {"amount": 105, "days": 30},
            "200": {"amount": 200, "days": 60},
            "280": {"amount": 280, "days": 90},
        }
        cfg = amount_map.get(raw, {"amount": 105, "days": 30})
        amount = cfg["amount"]
        days = cfg["days"]

    await call.answer("Генерируем платёжный счёт ЮKassa...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/billing/yookassa/create/",
                json={
                    "telegram_id": str(call.from_user.id),
                    "amount": amount,
                    "payment_method": "sbp"
                },
                headers={"Accept": "application/json"}
            )
            data = resp.json()
            checkout_url = data.get("checkout_url")
            if checkout_url:
                text = (
                    f"💳 <b>Счёт ЮKassa сформирован:</b>\n\n"
                    f"• Тариф: <b>{days} дней доступа</b>\n"
                    f"• Сумма к оплате: <b>{amount} ₽</b>\n"
                    f"• Способы: <b>СБП (без комиссии), Карты МИР, Сбер, Т-Банк</b>\n\n"
                    f"Нажмите кнопку ниже для безопасной оплаты на официальном шлюзе ЮKassa.\n"
                    f"После завершения платежа баланс будет начислен автоматически мгновенно!"
                )
                await call.message.edit_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=get_yookassa_pay_button(checkout_url, amount, days),
                    disable_web_page_preview=True
                )
                return
        except Exception as e:
            logger.error("Error creating YooKassa payment in bot: %s", e)

    await call.message.edit_text(
        "❌ Не удалось сформировать счёт ЮKassa. Попробуйте позже или используйте личный кабинет на сайте.",
        reply_markup=get_back_menu()
    )


@dp.callback_query(F.data == "pay_bepaid")
async def cb_pay_bepaid(call: CallbackQuery):
    await call.answer("Генерируем платёж bePaid...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/billing/bepaid/checkout/",
                json={"telegram_id": str(call.from_user.id)},
                headers={"Accept": "application/json"}
            )
            data = resp.json()
            checkout_url = data.get("checkout_url")
            if checkout_url:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🇧🇾 Оплатить 5.00 BYN (bePaid / ЕРИП)", url=checkout_url)],
                    [InlineKeyboardButton(text="◀️ Назад к балансу", callback_data="view_balance")]
                ])
                text = (
                    f"🇧🇾 <b>Оплата через bePaid (Беларусь):</b>\n\n"
                    f"• Сумма: <b>5.00 BYN (~150 ₽)</b>\n"
                    f"• Срок: <b>30 дней</b>\n"
                    f"• Способы: <b>Белкарт, ЕРИП, Visa, Mastercard, МИР</b>\n\n"
                    f"Нажмите кнопку ниже для безопасной оплаты:"
                )
                await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
                return
        except Exception as e:
            logger.error("Error creating bePaid payment in bot: %s", e)

    await call.message.edit_text("❌ Ошибка при создании платежа bePaid.", reply_markup=get_back_menu())


@dp.callback_query(F.data.in_(["view_whitelist", "toggle_whitelist"]))
async def cb_view_whitelist(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    vpn_info = data.get('vpn', {})
    whitelist_active = vpn_info.get('whitelist_enabled', True)
    custom_domains = vpn_info.get('custom_domains', [])
    custom_proxy = vpn_info.get('custom_proxy_domains', [])
    direct_zones = vpn_info.get('direct_zones', ['ru', 'by', 'su', 'рф'])

    ru_active = 'ru' in direct_zones
    by_active = 'by' in direct_zones

    ru_str = "🟢 <b>.ru, .рф:</b> НАПРЯМУЮ" if ru_active else "⚪ <b>.ru, .рф:</b> ЧЕРЕЗ VPN"
    by_str = "🟢 <b>.by:</b> НАПРЯМУЮ" if by_active else "⚪ <b>.by:</b> ЧЕРЕЗ VPN"

    dom_lines = []
    if custom_domains:
        for idx, dom in enumerate(custom_domains[:10], 1):
            dom_lines.append(f"  🟢 {idx}. <code>{dom}</code> (без VPN)")
    if custom_proxy:
        for idx, dom in enumerate(custom_proxy[:10], 1):
            dom_lines.append(f"  🚀 {idx}. <code>{dom}</code> (строго через VPN)")

    custom_str = "📋 <b>Ваши персональные сайты:</b>\n" + "\n".join(dom_lines) if dom_lines else "📋 <b>Персональные сайты:</b> <i>пока не добавлены</i>"

    routing_deeplink = vpn_info.get('routing_deeplink')

    text = (
        f"🛡️ <b>Настройка маршрутизации и исключений</b>\n\n"
        f"Сайты напрямую открываются с вашего домашнего IP (без расхода квоты и блокировок ВК/банков):\n\n"
        f"• {ru_str}\n"
        f"• {by_str}\n\n"
        f"{custom_str}\n\n"
        f"💡 <i>ВК, Mail.ru, банки, Госуслуги, Ozon, WB работают напрямую!</i>\n\n"
        f"ℹ️ <i>После изменения настроек просто нажмите «Обновить» (стрелочки) в приложении Incy.</i>"
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_whitelist_menu(
            whitelist_active,
            len(custom_domains),
            routing_deeplink,
            direct_zones=direct_zones,
            custom_proxy_count=len(custom_proxy)
        )
    )
    await call.answer()


@dp.callback_query(F.data.in_(["toggle_zone_ru", "toggle_zone_by"]))
async def cb_toggle_zone(call: CallbackQuery):
    zone = "ru" if call.data == "toggle_zone_ru" else "by"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/custom-whitelist/",
                json={"telegram_id": str(call.from_user.id), "action": "toggle_zone", "zone": zone}
            )
            res_data = resp.json()
            msg = res_data.get('message', 'Настройки зоны обновлены')
            await call.answer(msg, show_alert=True)
        except Exception as e:
            logger.error(f"Error toggling zone {zone}: {e}")
            await call.answer("Ошибка при переключении зоны", show_alert=True)
    return await cb_view_whitelist(call)


@dp.callback_query(F.data.in_(["toggle_ru_by", "toggle_whitelist_quick"]))
async def cb_toggle_ru_by(call: CallbackQuery):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/custom-whitelist/",
                json={"telegram_id": str(call.from_user.id), "action": "toggle_ru_by"}
            )
            res_data = resp.json()
            is_active = res_data.get('whitelist_enabled')
            msg = "✓ Обход РФ и РБ ВКЛЮЧЕН!" if is_active else "✓ Обход РФ и РБ ВЫКЛЮЧЕН (весь трафик в VPN)"
            await call.answer(msg, show_alert=True)
        except Exception as e:
            logger.error(f"Error toggling whitelist: {e}")
            await call.answer("Ошибка при переключении", show_alert=True)
    return await cb_view_whitelist(call)


@dp.callback_query(F.data == "add_proxy_site")
async def cb_add_proxy_site(call: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к белому списку", callback_data="view_whitelist")]
    ])
    text = (
        f"🚀 <b>Добавить сайт строго через VPN</b>\n\n"
        f"Отправьте мне в чат домен с префиксом <code>vpn</code>, например:\n"
        f"• <code>vpn blocked-news.ru</code>\n"
        f"• <code>vpn rutracker.org</code>\n\n"
        f"Этот сайт гарантированно пойдёт через сервер Франции, даже если он на .ru или .by!"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "clear_wl_sites")
async def cb_clear_wl_sites(call: CallbackQuery):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/custom-whitelist/",
                json={"telegram_id": str(call.from_user.id), "action": "clear"}
            )
            await call.answer("✓ Список персональных сайтов очищен!", show_alert=True)
        except Exception as e:
            logger.error(f"Error clearing whitelist: {e}")
            await call.answer("Ошибка при очистке списка", show_alert=True)
    return await cb_view_whitelist(call)


@dp.callback_query(F.data == "add_wl_site")
async def cb_add_wl_site(call: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к белому списку", callback_data="view_whitelist")]
    ])
    text = (
        f"➕ <b>Добавление сайта в белый список</b>\n\n"
        f"Просто <b>отправьте мне в чат</b> домен или адрес сайта, который нужно открывать <b>напрямую мимо VPN</b>.\n\n"
        f"Например:\n"
        f"• <code>mycompany.com</code>\n"
        f"• <code>game-server.net</code>\n"
        f"• <code>work-portal.by</code>\n\n"
        f"<i>(Можно отправить сразу несколько сайтов через запятую или пробел)</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "buy_turbo")
async def cb_buy_turbo(call: CallbackQuery):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/buy-traffic/",
                json={"telegram_id": str(call.from_user.id)}
            )
            res_data = resp.json()
            if res_data.get('success'):
                await call.answer("🚀 Добавлено +50 ГБ скоростного трафика!", show_alert=True)
            else:
                err_msg = res_data.get('error', 'Недостаточно средств на балансе (нужно 30 ₽)')
                await call.answer(f"⚠️ {err_msg}", show_alert=True)
        except Exception as e:
            logger.error(f"Error buying turbo traffic: {e}")
            await call.answer("Ошибка при покупке трафика", show_alert=True)

    await cb_main_menu(call)


@dp.callback_query(F.data == "download_app")
async def cb_download_app(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    vpn_info = data.get('vpn', {})
    connect_url = vpn_info.get('connect_url') or f"{SITE_URL}/dashboard/"

    text = (
        f"📲 <b>Шаг 1 из 2: Скачайте приложение INCY</b>\n\n"
        f"Выберите устройство и установите официальное бесплатное приложение:\n\n"
        f"🍏 <b>iPhone / iPad</b> — App Store\n"
        f"🤖 <b>Android</b> — Google Play\n"
        f"💻 <b>Компьютер</b> — Windows / Mac\n\n"
        f"👉 <i>После установки нажмите кнопку <b>«⚡ Шаг 2: Подключить в 1 клик»</b> внизу:</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_download_menu(connect_url))
    await call.answer()


@dp.callback_query(F.data == "view_devices")
async def cb_view_devices(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    devices_info = data.get('devices', {})
    conn_count = devices_info.get('connected_count', 1)
    max_dev = devices_info.get('max_devices', 5)
    dev_list = devices_info.get('devices', [])

    lines = []
    if dev_list:
        for idx, d in enumerate(dev_list, 1):
            status_icon = "🟢" if d.get('is_online') else "⚪"
            lines.append(f"{idx}. {d.get('icon', '📱')} <b>{d.get('name')}</b>\n   └ IP: <code>{d.get('masked_ip', '—')}</code> • {d.get('last_active')} [{status_icon}]")
    else:
        lines.append("<i>Нет активных устройств. Подключите VLESS ключ в приложении INCY.</i>")

    devices_text = "\n".join(lines)
    free_slots = max(0, max_dev - conn_count)

    text = (
        f"📱 <b>Управление устройствами ({conn_count} из {max_dev} онлайн)</b>\n\n"
        f"Ваша подписка поддерживает <b>до {max_dev} устройств одновременно</b> на одном ключе или подписке INCY.\n\n"
        f"<b>Активные устройства:</b>\n"
        f"{devices_text}\n\n"
        f"✨ <b>Свободных слотов:</b> {free_slots} из {max_dev}\n\n"
        f"💡 <i>Чтобы добавить новое устройство (iPhone, Android, Windows, Mac или Smart TV), просто установите INCY и нажмите «Подключить в 1 клик».</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_devices_menu(dev_list))
    await call.answer()


@dp.callback_query(F.data.startswith("del_dev_"))
async def cb_delete_device(call: CallbackQuery):
    dev_id = call.data.replace("del_dev_", "").strip()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/devices/delete/",
                json={
                    "telegram_id": str(call.from_user.id),
                    "device_id": dev_id
                }
            )
            res_data = resp.json()
            if res_data.get('success'):
                await call.answer("✓ Устройство успешно удалено! Слот освобожден.", show_alert=True)
            else:
                await call.answer(f"⚠️ {res_data.get('error', 'Не удалось удалить устройство.')}", show_alert=True)
        except Exception as e:
            logger.error(f"Error deleting device: {e}")
            await call.answer("⚠️ Ошибка соединения с сервером.", show_alert=True)
    return await cb_view_devices(call)


@dp.callback_query(F.data == "reset_devices")
async def cb_reset_devices(call: CallbackQuery):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/devices/reset/",
                json={"telegram_id": str(call.from_user.id)}
            )
            res_data = resp.json()
            if res_data.get('success'):
                await call.answer("✓ Все устройства сброшены! Все 5 слотов свободны.", show_alert=True)
            else:
                await call.answer("⚠️ Не удалось сбросить устройства.", show_alert=True)
        except Exception as e:
            logger.error(f"Error resetting devices: {e}")
            await call.answer("⚠️ Ошибка соединения с сервером.", show_alert=True)
    return await cb_view_devices(call)


@dp.callback_query(F.data == "view_referrals")
async def cb_view_referrals(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    user_info = data.get('user', {})
    ref_code = user_info.get('referral_code', '')
    site_ref_url = user_info.get('referral_url', f"{SITE_URL}/auth/register/?ref={ref_code}")
    bot_ref_url = f"https://t.me/{BOT_USERNAME}?start=ref_{ref_code}"
    refs_count = user_info.get('referrals_count', 0)

    text = (
        f"👥 <b>Реферальная программа VPN live-dev</b>\n\n"
        f"Приглашайте друзей и пользуйтесь быстрым VPN <b>абсолютно бесплатно!</b>\n\n"
        f"🎁 <b>Условия бонусов:</b>\n"
        f"• <b>+10.00 ₽ (+3 дня теста)</b> начисляются вам мгновенно, когда друг запускает бота!\n"
        f"• <b>+5 дней бесплатно</b> начисляются вам при первой оплате друга!\n"
        f"• Ваш друг сразу получает <b>3 дня бесплатного доступа</b>!\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: <b>{refs_count}</b>\n\n"
        f"🔗 <b>Ваша персональная ссылка для Telegram:</b>\n"
        f"<code>{bot_ref_url}</code>\n\n"
        f"🌐 <b>Ссылка для регистрации на сайте:</b>\n"
        f"<code>{site_ref_url}</code>"
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_referrals_menu(BOT_USERNAME, ref_code),
        disable_web_page_preview=True
    )
    await call.answer()


@dp.callback_query(F.data == "view_servers")
async def cb_view_servers(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    vpn_info = data.get('vpn', {})
    curr_server_id = vpn_info.get('server_id')

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{WEB_API_URL}/vpn/servers/")
            servers_data = resp.json().get('servers', [])
        except Exception:
            servers_data = []

    text = (
        f"🌍 <b>Выбор сервера и локации</b>\n\n"
        f"Текущий сервер: <b>{vpn_info.get('server_name', 'Франция • Париж')}</b>\n"
        f"Пинг: <b>{vpn_info.get('ping_ms', 38)} ms</b> | Канал: <b>1 Gbps</b>\n\n"
        f"Нажмите на локацию ниже для моментального переключения:"
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_servers_menu(servers_data, curr_server_id)
    )
    await call.answer()


@dp.callback_query(F.data.startswith("switch_srv_"))
async def cb_switch_server(call: CallbackQuery):
    srv_id_str = call.data.replace("switch_srv_", "")
    try:
        srv_id = int(srv_id_str)
    except ValueError:
        await call.answer("Неверный ID сервера", show_alert=True)
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/switch-server/",
                json={"telegram_id": str(call.from_user.id), "server_id": srv_id}
            )
            res_data = resp.json()
            if res_data.get('success'):
                srv_name = res_data.get('vpn', {}).get('clean_name', 'сервер')
                await call.answer(f"✓ Сервер переключен на {srv_name}!", show_alert=True)
            else:
                await call.answer("⚠️ Не удалось переключить сервер.", show_alert=True)
        except Exception as e:
            logger.error(f"Error switching server: {e}")
            await call.answer("⚠️ Ошибка соединения с сервером.", show_alert=True)

    return await cb_view_servers(call)


@dp.callback_query(F.data == "view_traffic")
async def cb_view_traffic(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    traffic_info = data.get('traffic', {})
    vpn_info = data.get('vpn', {})

    used_display = traffic_info.get('used_display', '0.0 МБ')
    limit_gb = traffic_info.get('limit_gb', 150)
    percent = traffic_info.get('percent', 0)
    left_gb = traffic_info.get('left_gb', 150)
    reset_date = traffic_info.get('reset_date', 'через 30 дней')

    # Visual progress bar (20 blocks)
    filled_blocks = min(20, max(0, int(percent / 5)))
    bar = "█" * filled_blocks + "░" * (20 - filled_blocks)

    text = (
        f"📊 <b>Статистика трафика и квоты</b>\n\n"
        f"• Использовано: <b>{used_display}</b> из <b>{limit_gb} ГБ</b>\n"
        f"• Осталось скоростного трафика: <b>{left_gb} ГБ</b>\n"
        f"• Использование квоты: <b>{percent}%</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"⚡ <b>Скорость:</b> 1 Gbps (без ограничений)\n"
        f"🔄 <b>Дата сброса квоты:</b> {reset_date}\n"
        f"🛡️ <b>Белый список РФ:</b> {'ВКЛ (банки и маркетплейсы не тратят квоту)' if vpn_info.get('whitelist_enabled') else 'ВЫКЛ'}\n\n"
        f"💡 <i>Весь российский трафик (Госуслуги, Сбер, Т-Банк, WB, Ozon) идет напрямую на максимальной скорости вашего провайдера.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_traffic_menu())
    await call.answer()


@dp.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    text = (
        f"💬 <b>Служба поддержки VPN live-dev</b>\n\n"
        f"Если у вас возникли сложности с подключением или оплатой, напишите нам в Telegram:\n\n"
        f"👉 <b>@{SUPPORT_TELEGRAM}</b>"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в поддержку", url=f"https://t.me/{SUPPORT_TELEGRAM}")],
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == "web_magic_login")
async def cb_web_magic_login(call: CallbackQuery):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/tg/generate-magic-link/",
                json={"telegram_id": str(call.from_user.id)}
            )
            res_data = resp.json()
            if res_data.get('success'):
                login_url = res_data.get('login_url')
                text = (
                    f"💻 <b>Вход в личный кабинет на ПК:</b>\n\n"
                    f"Нажмите на ссылку ниже, чтобы войти в кабинет на компьютере без пароля:\n\n"
                    f"👉 <a href=\"{login_url}\"><b>Войти в личный кабинет на сайте &rarr;</b></a>\n\n"
                    f"⏳ <i>Ссылка одноразовая и действует 15 минут.</i>"
                )
                await call.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
                await call.answer()
                return
            else:
                await call.answer(f"⚠️ {res_data.get('error', 'Ошибка генерации ссылки')}", show_alert=True)
        except Exception as e:
            logger.error(f"Error generating magic link: {e}")
            await call.answer("Ошибка при создании ссылки для входа", show_alert=True)


@dp.message(F.text.startswith('/promo'))
async def cmd_promo(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("ℹ️ Использование: <code>/promo КОД</code>\nНапример: <code>/promo WELCOME3</code>", parse_mode="HTML")
        return

    code_str = parts[1].strip()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/billing/activate-promo/",
                json={"telegram_id": str(message.from_user.id), "code": code_str}
            )
            data = resp.json()
            if data.get('success'):
                await message.answer(
                    f"🎉 <b>Промокод активирован!</b>\n{data.get('message')}\n\n"
                    f"Баланс: <b>{data.get('new_balance')} ₽</b> (хватит на {data.get('days_left')} дн.)",
                    parse_mode="HTML"
                )
            else:
                await message.answer(f"⚠️ {data.get('error', 'Не удалось активировать промокод')}", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error activating promo in bot: {e}")
            await message.answer("⚠️ Ошибка при активации промокода. Попробуйте позже.")


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_user_text_message(message: Message):
    text = (message.text or "").strip()
    is_proxy_req = text.lower().startswith("vpn ") or text.lower().startswith("впн ")
    action_type = "append_proxy" if is_proxy_req else "append"
    if is_proxy_req:
        clean_input = text.split(" ", 1)[1].strip()
    else:
        clean_input = text

    # Check if text looks like a domain or URL
    words = clean_input.replace(",", " ").split()
    has_domain = any("." in w and len(w) > 3 and not w.startswith("/") for w in words)
    if has_domain and len(clean_input) < 500:
        clean_text = clean_input.replace("http://", "").replace("https://", "").strip()
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(
                    f"{WEB_API_URL}/vpn/custom-whitelist/",
                    json={"telegram_id": str(message.from_user.id), "action": action_type, "domain": clean_text}
                )
                res_data = resp.json()
                if res_data.get('success'):
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🛡️ Открыть настройки", callback_data="view_whitelist")],
                        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")]
                    ])
                    route_desc = "<b>строго через VPN</b>" if is_proxy_req else "<b>напрямую без VPN</b>"
                    await message.answer(
                        f"✅ <b>Сайт(ы) успешно настроены!</b>\n\n"
                        f"Домены: <code>{clean_text}</code>\n"
                        f"Маршрут: {route_desc}\n\n"
                        f"ℹ️ <i>Нажмите «Обновить» (стрелочки) в приложении Incy, чтобы применить.</i>",
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                    return
            except Exception as e:
                logger.error(f"Error appending domain via chat: {e}")

    await cmd_start(message, CommandObject(command="start", args=None))


async def main():
    logger.info("Starting Telegram Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
