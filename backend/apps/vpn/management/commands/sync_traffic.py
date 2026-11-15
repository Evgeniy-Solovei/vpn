from django.core.management.base import BaseCommand
from apps.vpn.services import sync_traffic_from_3xui
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync traffic stats from 3X-UI SQLite database into VPNKey models'

    def handle(self, *args, **options):
        # 1. Sync traffic counters from 3X-UI SQLite DB
        updated = sync_traffic_from_3xui()
        self.stdout.write(self.style.SUCCESS(f"Successfully synced traffic for {updated} keys"))
