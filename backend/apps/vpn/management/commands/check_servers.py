import logging
from django.core.management.base import BaseCommand
from apps.vpn.services import check_all_servers_health_and_failover

logger = logging.getLogger('apps.vpn')

class Command(BaseCommand):
    help = "Checks health & latency of all VPN servers, detects RKN/TSPU bans, and auto-migrates affected users."

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Run silently without printing every server status',
        )
        parser.add_argument(
            '--mock',
            action='store_true',
            help='Dry run simulation without network socket calls',
        )

    def handle(self, *args, **options):
        quiet = options.get('quiet', False)
        is_mock = options.get('mock', False)
        if is_mock:
            self.stdout.write(self.style.SUCCESS("Dry mock mode: Серверов проверено: 3, статус: OK."))
            return

        if not quiet:
            self.stdout.write(self.style.NOTICE("🔍 Запуск проверки доступности серверов и детектора блокировок РКН..."))

        summary = check_all_servers_health_and_failover()
        checked = summary['servers_checked']
        migrated = summary['migrated_users_count']

        if not quiet:
            for s_id, res in summary['results'].items():
                status = res.get('status')
                ping = res.get('ping_ms')
                if status == 'online':
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Сервер #{s_id}: ONLINE ({ping} ms)"))
                elif status == 'blocked_rkn':
                    self.stdout.write(self.style.ERROR(f"  ✗ Сервер #{s_id}: BLOCKED_RKN (Таймаут/сброс)"))
                else:
                    self.stdout.write(self.style.WARNING(f"  ! Сервер #{s_id}: {status}"))

            self.stdout.write(self.style.SUCCESS(
                f"\nЗавершено. Проверено серверов: {checked}. Переведено пользователей на здоровые сервера: {migrated}."
            ))
