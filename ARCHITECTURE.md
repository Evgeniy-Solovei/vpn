# 🏗️ Техническая архитектура и документация: VPN Live Dev

## 1. Общая схема взаимодействия компонентов

```mermaid
flowchart TD
    subgraph Clients["Клиентский слой"]
        WebUser["Браузер (Десктоп / Мобилка)"]
        TgUser["Telegram App (Клиент)"]
        IncyApp["Приложение INCY / Happ / Hiddify"]
    end

    subgraph EntryPoint["Точка входа (Nginx Gateway)"]
        Nginx["Nginx Reverse Proxy :80/:443"]
    end

    subgraph CoreServices["Изолированные Docker Контейнеры"]
        Web["Django Backend (:8000)\n• Accounts & Auth\n• Billing & Tariffs\n• VPN Config Generator\n• Admin Panel"]
        MiniApp["Telegram Mini App (:80)\n• Nginx SPA Frontend\n• Haptic Feedback SDK"]
        Bot["Telegram Bot (aiogram 3.x)\n• Polling Worker\n• WebApp integration"]
        DB[(PostgreSQL 16)]
        Redis[(Redis 7)]
    end

    subgraph VpnInfrastructure["Зарубежная VPS Нода (Нидерланды)"]
        Xray["Xray-core / 3X-UI\n• VLESS-Reality (:443)\n• xtls-rprx-vision\n• SNI: www.microsoft.com"]
    end

    WebUser -->|HTTP / HTTPS| Nginx
    TgUser -->|MiniApp Webview| Nginx
    TgUser -->|Telegram Bot API| Bot
    IncyApp -->|Скачивание подписки /sub/| Nginx

    Nginx -->|/miniapp/| MiniApp
    Nginx -->|/, /api/, /admin/, /sub/| Web
    MiniApp -->|AJAX API Calls| Web
    Bot -->|REST API Calls :8000/api/| Web

    Web --> DB
    Web --> Redis
    Bot --> Redis
    Web -.->|3X-UI REST API / Sync| Xray
```

---

## 2. Белые списки РФ и РБ (Direct Routing)

### Проблема:
При использовании классических зарубежных VPN в России и Беларуси перестают работать:
* Банковские приложения (Сбер, Т-Банк, ВТБ, Альфа-Банк) из-за антифрод-защиты.
* Государственные сервисы (Госуслуги, Налог.ру, Мос.ру).
* Российские стриминги и маркетплейсы (Кинопоиск, Иви, Ozon, Wildberries, Авито, Яндекс.Маркет).

### Решение:
В подписке и PAC-скриптах настраивается динамическая маршрутизация:
1. **Правило `direct` (напрямую):**
   * Все доменные зоны: `.ru`, `.рф`, `.su`, `.by`.
   * Список критических государственных и банковских доменов.
2. **Правило `proxy` (через туннель VLESS Reality):**
   * Все заблокированные и зарубежные ресурсы: `instagram.com`, `facebook.com`, `twitter.com / x.com`, `youtube.com`, `googlevideo.com`, `chatgpt.com / openai.com`, торренты и медиа.
3. **Управление:**
   * В веб-кабинете и в Telegram-боте доступен тумблер `Белый список РФ`. При выключении весь трафик идет через Нидерланды (полезно для пользователей за рубежом, желающих скрыть свой IP полностью).

---

## 3. Схема базы данных (ERD)

```mermaid
erDiagram
    CustomUser ||--o{ VPNKey : "owns"
    CustomUser ||--o{ Transaction : "makes"
    CustomUser ||--o{ CustomUser : "invites (referral)"
    VPNServer ||--o{ VPNKey : "hosts"

    CustomUser {
        int id PK
        string username
        string email
        string telegram_id
        decimal balance
        decimal daily_deduction
        boolean autopay
        string referral_code
        datetime created_at
    }

    VPNServer {
        int id PK
        string name
        string country_code
        string ip
        int port
        string reality_sni
        string reality_pbk
        string reality_short_id
        int ping_ms
        boolean is_active
    }

    VPNKey {
        int id PK
        uuid key_uuid
        string sub_token
        boolean whitelist_enabled
        boolean is_active
        datetime created_at
    }

    Transaction {
        int id PK
        decimal amount
        string payment_method
        string status
        string external_id
        datetime created_at
    }
```

---

## 4. Спецификация REST API (`/api/`)

| Метод | URL | Описание | Параметры |
|---|---|---|---|
| `POST` | `/api/tg/sync/` | Синхронизация Telegram пользователя с бэкендом (создание ключа, возврат баланса) | `telegram_id`, `telegram_username`, `ref_code` |
| `POST` | `/api/vpn/toggle-whitelist/` | Переключение белого списка РФ для ключа | `telegram_id` или `user_id` |
| `GET` | `/api/vpn/servers/` | Список доступных локаций и их пинг | — |
| `GET` | `/api/billing/tariffs/` | Список активных тарифных планов | — |
| `GET` | `/sub/<sub_token>/` | Универсальная Base64 подписка для INCY / Happ | — |
| `GET` | `/vpn/pac/<sub_token>/` | PAC-скрипт авто-прокси для подключения без программ | — |
| `GET` | `/vpn/qr/<sub_token>/` | PNG/SVG изображение QR-кода ключа | — |

---

## 5. Модель монетизации и списаний (Daily Billing)

* **Посуточное списание:**
  * Вместо блокировки доступа на месяц сервис списывает фиксированную сумму в день (по умолчанию **3.50 ₽ / сутки**).
  * Позволяет привлекать пользователей с небольшим бюджетом (можно положить 50–100 ₽ и пользоваться 2–4 недели).
* **Триал период:**
  * Каждому новому пользователю при регистрации начисляется **15.00 ₽** (3 дня бесплатного быстрого доступа для проверки качества).
* **Реферальная система:**
  * За каждого приглашенного пользователя, зарегистрировавшегося по реферальной ссылке, пригласившему начисляется **+10.00 ₽** на баланс.
