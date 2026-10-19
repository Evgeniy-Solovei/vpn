import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

from bot.config import BOT_TOKEN, WEB_API_URL, SITE_URL
from bot.keyboards.inline import get_main_menu, get_back_menu, get_download_menu

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
    ref_code = command.args if command.args else None

    data = await sync_user_with_backend(telegram_id, username, ref_code)
    user_info = data.get('user', {})
    vpn_info = data.get('vpn', {})
    traffic_info = data.get('traffic', {})

    server_title = vpn_info.get('server_name') or '🇳🇱 Нидерланды • Амстердам'
    current_speed = traffic_info.get('current_speed', '500 Мб/с')
    left_gb = traffic_info.get('left_gb', 200)
    limit_gb = traffic_info.get('limit_gb', 200)

    welcome_text = (
        f"👋 <b>Добро пожаловать в VPN live-dev!</b>\n\n"
        f"⚡ <b>Быстрый и защищенный VPN без блокировок для РФ и РБ.</b>\n"
        f"• Протокол нового поколения: <b>VLESS Reality</b> (маскировка под чистый трафик)\n"
        f"• Сервер: <b>{server_title}</b> (Пинг: {vpn_info.get('ping_ms', 42)} ms)\n"
        f"• Скорость: <b>{current_speed}</b> (Остаток квоты: {left_gb}/{limit_gb} ГБ)\n"
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

    server_title = vpn_info.get('server_name') or '🇳🇱 Нидерланды • Амстердам'
    current_speed = traffic_info.get('current_speed', '500 Мб/с')
    left_gb = traffic_info.get('left_gb', 200)
    limit_gb = traffic_info.get('limit_gb', 200)

    text = (
        f"🏠 <b>Главное меню VPN live-dev</b>\n\n"
        f"• Баланс: <b>{user_info.get('balance', 0)} ₽</b> (на {user_info.get('days_left', 0)} дн.)\n"
        f"• Сервер: <b>{server_title}</b>\n"
        f"• Скорость канала: <b>{current_speed}</b> ({left_gb}/{limit_gb} ГБ)\n"
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

    text = (
        f"🔑 <b>Ваш персональный VLESS Reality ключ:</b>\n\n"
        f"<code>{vless_url}</code>\n\n"
        f"🔗 <b>Ссылка на автообновляемую подписку:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        f"💡 <i>Скопируйте ключ или подписку и вставьте в клиент <b>INCY</b>, Happ или Hiddify.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_menu())
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
        f"Для пополнения баланса перейдите в личный кабинет на сайте:\n"
        f"👉 <a href='{SITE_URL}/billing/tariffs/'>Пополнить баланс онлайн</a> (СБП, Карты РФ, Крипта)"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_menu(), disable_web_page_preview=True)
    await call.answer()


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
        f"Если у вас возникли сложности с подключением или оплатой, напишите нам:\n"
        f"• Официальный канал новостей: @live_dev_news\n"
        f"• Чат поддержки: @live_dev_support\n\n"
        f"Мы отвечаем в течение 10–15 минут!"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_menu())
    await call.answer()


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
