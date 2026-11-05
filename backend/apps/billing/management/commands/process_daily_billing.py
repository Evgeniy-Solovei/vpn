from django.core.management.base import BaseCommand
from apps.accounts.models import CustomUser
from apps.billing.models import notify_telegram_user

class Command(BaseCommand):
    help = "Processes daily fee deductions for all users, sends notifications, and disables expired VPN keys"

    def handle(self, *args, **options):
        users = CustomUser.objects.all()
        total_charged_users = 0
        total_days = 0
        expired_count = 0

        for u in users:
            try:
                was_active = u.has_active_subscription
                days = u.apply_daily_deductions()
                if days > 0:
                    total_charged_users += 1
                    total_days += days
                    self.stdout.write(f"Charged {u.username}: {days} days, new balance: {u.balance} ₽")

                # Notify users when subscription expires or is about to expire
                if was_active and not u.has_active_subscription:
                    expired_count += 1
                    msg = (
                        "⛔️ <b>Ваша подписка VPN live-dev истекла.</b>\n\n"
                        "Баланс: 0.00 ₽. Доступ к VPN временно приостановлен.\n\n"
                        "💡 <i>Пополните баланс в боте или на сайте https://vpn.live-dev.by, "
                        "чтобы мгновенно возобновить интернет!</i>"
                    )
                    notify_telegram_user(u, msg)
                elif u.has_active_subscription and not (u.is_staff or u.is_superuser) and u.days_left == 1:
                    msg = (
                        "⚠️ <b>Внимание: остался 1 день подписки VPN live-dev!</b>\n\n"
                        f"Текущий баланс: {u.balance} ₽.\n"
                        "Завтра доступ будет приостановлен. Пополните баланс заранее, чтобы не терять связь."
                    )
                    notify_telegram_user(u, msg)
            except Exception as e:
                self.stderr.write(f"Error charging user {u.username}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed daily billing: {total_charged_users} users charged ({total_days} total days). Expired: {expired_count}"
        ))
