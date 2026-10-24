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

    # 1. Create or update Real France Server
    servers_data = [
        {
            "country_code": "FR",
            "country_name": "Франция",
            "city": "Париж",
            "name": "Франция • Париж",
            "ip": "81.19.137.255",
            "port": 443,
            "reality_sni": "dl.google.com",
            "reality_pbk": "yq8Rau8sF3wZ48kXb7x7_Y2o_F-qK9wz8L_X-QyA6iE",
            "reality_short_id": "d8e4f1a2b3c5",
            "ping_ms": 38,
            "load_percent": 18,
            "speed_description": "1 Gbps • Безлимит",
            "is_active": True,
            "server_type": "direct",
            "order": 1,
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

    # Re-point all keys to real France server and delete fake servers
    VPNKey.objects.all().update(server=primary_server)
    VPNServer.objects.exclude(id=primary_server.id).delete()
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
    demo_key = VPNKey.objects.filter(user=demo_user).first()
    if not demo_key:
        demo_key = VPNKey.objects.create(user=demo_user, server=server)
    else:
        demo_key.server = server
        demo_key.save()
    print(f"✅ Демо-пользователь: логин 'demo' | пароль 'demo123' (Баланс 105 ₽)")

    # 5. Promo Codes (3, 5, 10 days)
    from apps.billing.models import PromoCode
    promos = [
        {"code": "WELCOME3", "days": 3, "max_uses": 5000},
        {"code": "SORRY5", "days": 5, "max_uses": 1000},
        {"code": "TURBO10", "days": 10, "max_uses": 500},
    ]
    for p_data in promos:
        p, _ = PromoCode.objects.get_or_create(
            code=p_data["code"],
            defaults={"days": p_data["days"], "max_uses": p_data["max_uses"], "is_active": True}
        )
        print(f"✅ Промокод: {p.code} (+{p.days} дней)")

    print("\n🎉 Готово! Все демо-данные успешно загружены.")

if __name__ == '__main__':
    seed()
