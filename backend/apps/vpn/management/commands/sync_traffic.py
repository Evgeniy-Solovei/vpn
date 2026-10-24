from django.core.management.base import BaseCommand
from apps.vpn.services import sync_traffic_from_3xui, sync_all_keys_to_panel
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sync traffic stats from 3X-UI SQLite database into VPNKey models'

    def handle(self, *args, **options):
        # 1. Sync traffic
        updated = sync_traffic_from_3xui()
        self.stdout.write(self.style.SUCCESS(f"Successfully synced traffic for {updated} keys"))
        # 2. Ensure all active keys are registered in 3X-UI panel
        keys_synced = sync_all_keys_to_panel()
        self.stdout.write(self.style.SUCCESS(f"Ensured {keys_synced} active keys in 3X-UI inbound"))
