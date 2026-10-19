import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.vpn.models import VPNServer, VPNKey
from apps.vpn.services import get_or_create_default_server
from apps.billing.models import TariffPlan

User = get_user_model()

def seed():
    print("🌱 Инициализация демо-данных для локального просмотра...")

    # 1. Create or get default VPN Server
    server = get_or_create_default_server()
    print(f"✅ VPN Сервер: {server.name} ({server.country_name})")

    # 2. Create or get Tariff Plans
    plan1, _ = TariffPlan.objects.get_or_create(
        code="blackrock",
        defaults={
            "name": "BLACKROCK",
            "daily_price": Decimal("4.50"),
            "speed_mbps": 500,
            "description": "500 Мб/с пропускной канал. Комфортные сервера, 2 страны на выбор.",
            "is_featured": True,
            "is_active": True,
        }
    )
    plan2, _ = TariffPlan.objects.get_or_create(
        code="blackeasy",
        defaults={
            "name": "BLACKEASY",
            "daily_price": Decimal("2.40"),
            "speed_mbps": 50,
            "description": "50 Мб/с пропускной канал. Доступ к популярным сервисам.",
            "is_featured": False,
            "is_active": True,
        }
    )
    print("✅ Тарифные планы: BLACKROCK, BLACKEASY")

    # 3. Superuser Admin
    admin_user, admin_created = User.objects.get_or_create(
        username="admin",
        defaults={
            "email": "admin@live-dev.by",
            "is_staff": True,
            "is_superuser": True,
            "balance": Decimal("500.00"),
        }
    )
    admin_user.set_password("admin123")
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.save()
    VPNKey.objects.get_or_create(user=admin_user, server=server)
    print(f"✅ Администратор: логин 'admin' | пароль 'admin123'")

    # 4. Demo User
    demo_user, demo_created = User.objects.get_or_create(
        username="demo",
        defaults={
            "email": "demo@live-dev.by",
            "balance": Decimal("105.00"), # 30 days
            "daily_deduction": Decimal("3.50"),
            "autopay": True,
        }
    )
    demo_user.set_password("demo123")
    demo_user.balance = Decimal("105.00")
    demo_user.save()
    demo_key, _ = VPNKey.objects.get_or_create(user=demo_user, server=server)
    print(f"✅ Демо-пользователь: логин 'demo' | пароль 'demo123' (Баланс 105 ₽)")

    print("\n🎉 Готово! Все демо-данные успешно загружены.")

if __name__ == '__main__':
    seed()
