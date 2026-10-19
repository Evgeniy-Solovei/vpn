from datetime import date
from django.core.management.base import BaseCommand
from apps.vpn.models import VPNKey

class Command(BaseCommand):
    help = "Resets monthly VPN traffic quota for users whose reset date has arrived."

    def handle(self, *args, **options):
        today = date.today()
        keys_to_reset = VPNKey.objects.filter(traffic_reset_date__lte=today)
        count = keys_to_reset.count()

        for key in keys_to_reset:
            key.reset_monthly_traffic()

        self.stdout.write(self.style.SUCCESS(f"Successfully reset monthly traffic for {count} VPN keys."))
