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

    # 1. Create or update European High-Speed VPN Servers
    servers_data = [
        {
            "country_code": "NL",
            "country_name": "Нидерланды",
            "city": "Амстердам",
            "name": "Нидерланды • Амстердам",
            "ip": "89.110.100.12",
            "port": 443,
            "ping_ms": 42,
            "load_percent": 24,
            "speed_description": "1 Gbps • Безлимит",
            "is_active": True,
        },
        {
            "country_code": "DE",
            "country_name": "Германия",
            "city": "Франкфурт",
            "name": "Германия • Франкфурт",
            "ip": "45.142.214.55",
            "port": 443,
            "ping_ms": 38,
            "load_percent": 31,
            "speed_description": "1 Gbps • Безлимит",
            "is_active": True,
        },
        {
            "country_code": "FI",
            "country_name": "Финляндия",
            "city": "Хельсинки",
            "name": "Финляндия • Хельсинки",
            "ip": "65.21.144.80",
            "port": 443,
            "ping_ms": 27,
            "load_percent": 18,
            "speed_description": "1 Gbps • Безлимит",
            "is_active": True,
        },
    ]

    primary_server = None
    for s_info in servers_data:
        s, _ = VPNServer.objects.update_or_create(
            country_code=s_info["country_code"],
            city=s_info["city"],
            defaults=s_info
        )
        if not primary_server:
            primary_server = s
        print(f"✅ VPN Сервер: {s.display_name} ({s.speed_description}, {s.ping_ms} ms)")

    # Clean any legacy servers with '01'
    VPNServer.objects.filter(name__contains='01').exclude(id=primary_server.id).delete()
    if '01' in primary_server.name:
        primary_server.name = "Нидерланды • Амстердам"
        primary_server.save()
    server = primary_server


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
