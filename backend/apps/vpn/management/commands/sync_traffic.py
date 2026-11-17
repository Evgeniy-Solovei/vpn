from django.core.management.base import BaseCommand
from apps.vpn.services import sync_traffic_from_3xui, audit_users_connection_health
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync traffic stats from 3X-UI SQLite database and auto-audit user connection health'

    def handle(self, *args, **options):
        # 1. Sync traffic counters from 3X-UI SQLite DB
        updated = sync_traffic_from_3xui()
        self.stdout.write(self.style.SUCCESS(f"Successfully synced traffic for {updated} keys"))

        # 2. Autonomous user health scan: detect stalls, dropped packets, missing inbounds
        audit_res = audit_users_connection_health()
        stalls = audit_res.get('stalls_found', 0)
        if stalls > 0:
            self.stdout.write(self.style.WARNING(f"⚠️ Обнаружено зависших сессий: {stalls}. Администратор оповещен в Telegram."))
