import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from bot.config import BOT_TOKEN, WEB_API_URL, SITE_URL, SUPPORT_TELEGRAM
from bot.keyboards.inline import (
    get_main_menu,
    get_back_menu,
    get_download_menu,
    get_balance_menu,
    get_yookassa_tariffs_menu,
    get_yookassa_pay_button,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
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

    ref_code = raw_arg if raw_arg and not raw_arg.startswith('link_') else None

    data = await sync_user_with_backend(telegram_id, username, ref_code)
    user_info = data.get('user', {})
    vpn_info = data.get('vpn', {})
    traffic_info = data.get('traffic', {})

    server_title = vpn_info.get('server_name') or '🇫🇷 Франция • Париж'
    ping_ms = vpn_info.get('ping_ms', 38)
    used_display = traffic_info.get('used_display', '0.0 МБ')
    is_unlimited = traffic_info.get('is_unlimited', True) or not traffic_info.get('limit_gb')

    if is_unlimited:
        traffic_line = f"• Трафик: <b>{used_display}</b> (Безлимит ∞)"
    else:
        traffic_line = f"• Трафик: <b>{traffic_info.get('used_gb', 0)} / {traffic_info.get('limit_gb', 0)} ГБ</b>"

    welcome_text = (
        f"👋 <b>Добро пожаловать в VPN live-dev!</b>\n\n"
        f"⚡ <b>Быстрый и защищенный VPN без блокировок для РФ и РБ.</b>\n"
        f"• Протокол нового поколения: <b>VLESS Reality</b> (маскировка под чистый трафик)\n"
        f"• Активная локация: <b>{server_title}</b> (Пинг: {ping_ms} ms)\n"
        f"• Скорость: <b>1 Gbps</b>\n"
        f"{traffic_line}\n"
        f"• Белый список РФ: <b>Госуслуги, Сбер, Т-Банк и маркетплейсы работают напрямую!</b>\n\n"
        f"💰 Ваш баланс: <b>{user_info.get('balance', 15.0)} ₽</b> (хватит на {user_info.get('days_left', 3)} дн.)\n\n"
        f"👇 <i>Нажмите «Подключить в 1 клик» для моментальной настройки приложения INCY:</i>"
    )

    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_menu(vpn_info, user_info)
    )


@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    user_info = data.get('user', {})
    vpn_info = data.get('vpn', {})
    traffic_info = data.get('traffic', {})

    server_title = vpn_info.get('server_name') or '🇫🇷 Франция • Париж'
    ping_ms = vpn_info.get('ping_ms', 38)
    used_display = traffic_info.get('used_display', '0.0 МБ')
    is_unlimited = traffic_info.get('is_unlimited', True) or not traffic_info.get('limit_gb')

    if is_unlimited:
        traffic_line = f"• Трафик: <b>{used_display}</b> (Безлимит ∞)"
    else:
        traffic_line = f"• Трафик: <b>{traffic_info.get('used_gb', 0)} / {traffic_info.get('limit_gb', 0)} ГБ</b>"

    text = (
        f"🏠 <b>Главное меню VPN live-dev</b>\n\n"
        f"• Баланс: <b>{user_info.get('balance', 0)} ₽</b> (на {user_info.get('days_left', 0)} дн.)\n"
        f"• Активная локация: <b>{server_title}</b> ({ping_ms} ms)\n"
        f"• Скорость: <b>1 Gbps</b>\n"
        f"{traffic_line}\n"
        f"• Белый список РФ: {'<b>ВКЛ (банки напрямую)</b>' if vpn_info.get('whitelist_enabled') else '<b>ВЫКЛ (весь трафик в VPN)</b>'}"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu(vpn_info, user_info))
    await call.answer()


@dp.callback_query(F.data == "view_key")
async def cb_view_key(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    vpn_info = data.get('vpn', {})
    vless_url = vpn_info.get('vless_url', '')
    sub_url = vpn_info.get('sub_url', '')

    max_dev = vpn_info.get('max_devices', 5)
    text = (
        f"🔑 <b>Ваш персональный VLESS Reality ключ:</b>\n\n"
        f"<code>{vless_url}</code>\n\n"
        f"🔗 <b>Ссылка на автообновляемую подписку:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        f"📱 <b>Лимит:</b> до {max_dev} устройств одновременно (телефон, ПК, планшет, Smart TV)\n\n"
        f"💡 <b>Как подключить за 2 шага:</b>\n"
        f"1. Установите приложение <b>INCY</b> (кнопка ниже)\n"
        f"2. Нажмите <b>«⚡ Подключить в 1 клик (INCY)»</b> для моментальной настройки\n"
        f"<i>(Либо скопируйте ключ выше и вставьте в INCY через «+»)</i> 🚀"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Подключить в 1 клик (INCY)", url=vpn_info.get('connect_url') or f"{SITE_URL}/dashboard/")],
        [InlineKeyboardButton(text="📲 Скачать приложение", callback_data="download_app")],
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


@dp.callback_query(F.data == "toggle_whitelist")
async def cb_toggle_whitelist(call: CallbackQuery):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{WEB_API_URL}/vpn/toggle-whitelist/",
                json={"telegram_id": str(call.from_user.id)}
            )
            res_data = resp.json()
            is_active = res_data.get('whitelist_enabled')
            msg = "Белый список ВКЛ: Госуслуги и банки идут напрямую!" if is_active else "Белый список ВЫКЛ: весь трафик через VPN"
            await call.answer(msg, show_alert=True)
        except Exception as e:
            logger.error(f"Error toggling whitelist: {e}")
            await call.answer("Ошибка при переключении", show_alert=True)

    # Refresh menu
    await cb_main_menu(call)


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
    text = (
        f"📲 <b>Скачать рекомендуемое приложение: INCY</b>\n\n"
        f"INCY — нативный клиент для VLESS Reality на всех платформах:\n"
        f"• Поддержка iOS, Android, macOS, Windows, Linux, Android TV\n"
        f"• Моментальный импорт в 1 клик\n"
        f"• Функция Send to TV для подключения телевизора"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_download_menu())
    await call.answer()


@dp.callback_query(F.data == "view_referrals")
async def cb_view_referrals(call: CallbackQuery):
    data = await sync_user_with_backend(call.from_user.id, call.from_user.username)
    user_info = data.get('user', {})
    ref_url = user_info.get('referral_url', '')

    text = (
        f"👥 <b>Реферальная программа VPN live-dev</b>\n\n"
        f"🎁 Приглашайте друзей и получайте <b>+5 дней бесплатно</b> за каждого приглашенного друга при его первой оплате!\n\n"
        f"Ваша персональная ссылка:\n"
        f"<code>{ref_url}</code>\n\n"
        f"Приглашено друзей: <b>{user_info.get('referrals_count', 0)}</b>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_menu())
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


async def main():
    logger.info("Starting Telegram Bot...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
