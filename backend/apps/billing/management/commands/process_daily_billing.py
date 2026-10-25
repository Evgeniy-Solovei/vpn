from django.core.management.base import BaseCommand
from apps.accounts.models import CustomUser

class Command(BaseCommand):
    help = "Processes daily fee deductions for all users and disables expired VPN keys"

    def handle(self, *args, **options):
        users = CustomUser.objects.all()
        total_charged_users = 0
        total_days = 0
        expired_count = 0

        for u in users:
            try:
                days = u.apply_daily_deductions()
                if days > 0:
                    total_charged_users += 1
                    total_days += days
                    self.stdout.write(f"Charged {u.username}: {days} days, new balance: {u.balance} ₽")
                if not u.has_active_subscription:
                    expired_count += 1
            except Exception as e:
                self.stderr.write(f"Error charging user {u.username}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed daily billing: {total_charged_users} users charged ({total_days} total days). Expired: {expired_count}"
        ))
