"""Create (or reset) the public demo account with realistic data.

Run:  .venv/Scripts/python.exe scripts/seed_demo.py [API_URL]

The demo account is a REAL account (demo@xabarchi.uz / demo1234) seeded
through the public API wherever possible — devices pair via /devices/pair,
messages flow through send -> gateway claim/ack/report, and so on. Direct
SQL is used only for what the API deliberately doesn't allow: upgrading the
plan without payment, backdating history, bot subscribers, notifications,
and invoices.

Re-running the script wipes the demo account's data and reseeds it, so it
doubles as a "reset demo" job (safe to put on a cron).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv()

API = (sys.argv[1] if len(sys.argv) > 1 else "https://manager-xabarchi-backend-bula2s-f6aaa1-13-140-185-49.sslip.io").rstrip("/") + "/api/v1"
DATABASE_URL = os.environ["DATABASE_URL"]

DEMO_EMAIL = "demo@xabarchi.uz"
DEMO_PASSWORD = "demo1234"

random.seed(42)  # deterministic demo data on every reset

GROUPS = [("Mijozlar", "#0E9488"), ("VIP mijozlar", "#C89B3C"), ("Yetkazib berish", "#5B8DEF")]

CONTACTS = [
    ("Jasur", "Karimov", "998901234567", "Samarqand Express", [0, 1]),
    ("Dilnoza", "Rashidova", "998935557713", "Orzu Market", [0]),
    ("Bekzod", "Tashkentov", "998917822440", None, [0, 2]),
    ("Malika", "Yusupova", "998972149005", "Chimgan Tour", [1]),
    ("Sardor", "Aliyev", "998884021176", None, [0]),
    ("Nigora", "Islomova", "998941183052", "Bella Gul", [0, 1]),
    ("Rustam", "Nazarov", "998909998877", "TezKuryer", [2]),
    ("Zilola", "Hamidova", "998933216654", None, [0]),
    ("Otabek", "Ergashev", "998971112233", "MegaStroy", [0, 2]),
    ("Kamola", "Saidova", "998905556677", None, [1]),
    ("Farrux", "Umarov", "998936667788", "IT Park", [0]),
    ("Gulbahor", "Tosheva", "998918889900", None, [0]),
]

TEMPLATES = [
    ("Tasdiqlash kodi", "Tasdiqlash kodingiz: {kod}. Uni hech kimga bermang!"),
    ("Buyurtma qabul qilindi", "Hurmatli {ism}, buyurtmangiz #{raqam} qabul qilindi. Yetkazish: {sana}"),
    ("Yetkazildi", "{ism}, buyurtmangiz manzilga yetkazildi. Xaridingiz uchun rahmat!"),
    ("Aksiya", "{ism}, faqat shu hafta: barcha mahsulotlarga {chegirma}% chegirma! Batafsil: xabarchi.uz"),
]

SMS_TEXTS = [
    "Tasdiqlash kodingiz: {}. Uni hech kimga bermang!",
    "Buyurtmangiz #{} qabul qilindi. Tez orada yetkazamiz.",
    "Buyurtmangiz manzilga yetkazildi. Xaridingiz uchun rahmat!",
    "Faqat shu hafta: 20% chegirma! Batafsil: xabarchi.uz",
    "Eslatma: ertaga soat 15:00 da uchrashuvingiz bor.",
]


def step(name: str, detail: str = "") -> None:
    print(f"  [ok] {name}" + (f" — {detail}" if detail else ""))


async def api_call(client: httpx.AsyncClient, method: str, path: str, *, token: str | None = None, json: dict | None = None, expect: tuple[int, ...] = (200, 201)) -> dict | list | None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.request(method, f"{API}{path}", headers=headers, json=json)
    if response.status_code not in expect:
        raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:200]}")
    return response.json() if response.status_code != 204 else None


async def main() -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        # ---- account: login or first-time register --------------------
        response = await client.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        if response.status_code == 200:
            auth = response.json()
        else:
            auth = await api_call(client, "POST", "/auth/register", json={
                "firstName": "Demo", "lastName": "Foydalanuvchi", "email": DEMO_EMAIL,
                "phone": "998712000000", "company": "Xabarchi Demo", "password": DEMO_PASSWORD,
            })
        token = auth["accessToken"]
        user_id = uuid.UUID(auth["user"]["id"])
        step("account", str(user_id))

        # ---- reset all previous demo data (SQL) -----------------------
        db = await asyncpg.connect(DATABASE_URL)
        try:
            await db.execute("DELETE FROM messages WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM bot_broadcasts WHERE bot_id IN (SELECT id FROM telegram_bots WHERE user_id=$1)", user_id)
            await db.execute("DELETE FROM bot_subscribers WHERE bot_id IN (SELECT id FROM telegram_bots WHERE user_id=$1)", user_id)
            await db.execute("DELETE FROM telegram_bots WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM contact_group_members WHERE contact_id IN (SELECT id FROM contacts WHERE user_id=$1)", user_id)
            await db.execute("DELETE FROM contacts WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM contact_groups WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM templates WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM notifications WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM api_keys WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM devices WHERE user_id=$1", user_id)
            await db.execute("DELETE FROM invoices WHERE user_id=$1", user_id)
            # plan_expires_at far in the future so the demo stays active behind
            # the paywall (sending + pairing keep working during/after seeding).
            await db.execute(
                """UPDATE users SET plan_id='biznes', email_verified_at=now(), sms_sent_this_month=0,
                   plan_expires_at=now() + interval '10 years',
                   first_name='Demo', last_name='Foydalanuvchi', company='Xabarchi Demo',
                   phone='998712000000', avatar_hue=172, password_hash=users.password_hash
                   WHERE id=$1""",
                user_id,
            )
            step("reset", "old demo data wiped, plan=biznes (active), email verified")

            # ---- devices (real pairing API) ---------------------------
            device_specs = [
                {"name": "Ofis — asosiy", "model": "Samsung Galaxy A54", "phone": "998901112233", "operator": "Ucell", "androidVersion": "14", "appVersion": "2.4.1", "dailyLimit": 800},
                {"name": "Sklad", "model": "Redmi Note 12", "phone": "998935550011", "operator": "Beeline", "androidVersion": "13", "appVersion": "2.4.1", "dailyLimit": 500},
                {"name": "Zaxira telefon", "model": "Pixel 6a", "phone": "998977781255", "operator": "UMS", "androidVersion": "15", "appVersion": "2.3.9", "dailyLimit": 400},
            ]
            device_tokens: list[str] = []
            for spec in device_specs:
                pair = await api_call(client, "POST", "/devices/pair", token=token, json=spec)
                device_tokens.append(pair["token"])
            step("devices", f"{len(device_tokens)} paired")

            # ---- contacts + groups ------------------------------------
            group_ids = []
            for name, color in GROUPS:
                group = await api_call(client, "POST", "/contacts/groups", token=token, json={"name": name, "color": color})
                group_ids.append(group["id"])
            contact_phones = []
            for first, last, phone, company, groups in CONTACTS:
                await api_call(client, "POST", "/contacts", token=token, json={
                    "firstName": first, "lastName": last, "phone": phone, "company": company,
                    "groupIds": [group_ids[i] for i in groups],
                })
                contact_phones.append(phone)
            step("contacts", f"{len(contact_phones)} contacts, {len(group_ids)} groups")

            # ---- templates --------------------------------------------
            for name, text in TEMPLATES:
                await api_call(client, "POST", "/templates", token=token, json={"name": name, "text": text})
            step("templates", str(len(TEMPLATES)))

            # ---- message history (real send -> claim -> report) -------
            # Round A: 28 messages in 5 batched sends (rate limit friendly).
            batches = [
                (contact_phones[0:3], SMS_TEXTS[0].format(4821), "urgent"),
                (contact_phones[3:9], SMS_TEXTS[1].format(1042), "transactional"),
                (contact_phones[0:5], SMS_TEXTS[2], "transactional"),
                (contact_phones[4:12], SMS_TEXTS[3], "bulk"),
                (contact_phones[6:12], SMS_TEXTS[4], "bulk"),
            ]
            for to, text, priority in batches:
                await api_call(client, "POST", "/messages", token=token, json={"to": to, "text": text, "priority": priority})

            gateway = {"X-Device-Token": device_tokens[0]}
            claimed = (await client.post(f"{API}/gateway/claim", headers=gateway, json={"limit": 28})).json()
            ids = [m["id"] for m in claimed]
            await client.post(f"{API}/gateway/ack", headers=gateway, json={"ids": ids})
            fail_reasons = {ids[5]: "no_signal", ids[13]: "invalid_number", ids[21]: "device_offline"}
            for message_id in ids:
                if message_id in fail_reasons:
                    body = {"id": message_id, "status": "failed", "failReason": fail_reasons[message_id]}
                else:
                    body = {"id": message_id, "status": "delivered"}
                await client.post(f"{API}/gateway/report", headers=gateway, json=body)
            step("history round", f"{len(ids)} sent (3 failed)")

            # Backdate round A over the previous 12 days (same month, so we
            # stay inside the 2026-08 partition).
            for index, message_id in enumerate(ids):
                days_back = 1 + (index % 12)
                hour = random.randint(9, 20)
                base = datetime.now(UTC).replace(hour=hour, minute=random.randint(0, 59)) - timedelta(days=days_back)
                await db.execute(
                    """UPDATE messages SET created_at=$2::timestamptz,
                       sent_at=$2::timestamptz + interval '8 seconds',
                       delivered_at = CASE WHEN status='delivered' THEN $2::timestamptz + interval '31 seconds' END
                       WHERE id=$1""",
                    message_id, base,
                )
            step("backdate", "history spread over the last 12 days")

            # Round B: today's live activity — some delivered, some queued.
            await api_call(client, "POST", "/messages", token=token, json={
                "to": contact_phones[0:6],
                "text": SMS_TEXTS[1].format(7153),
                "priority": "transactional",
            })
            gateway2 = {"X-Device-Token": device_tokens[1]}
            claimed2 = (await client.post(f"{API}/gateway/claim", headers=gateway2, json={"limit": 4})).json()
            ids2 = [m["id"] for m in claimed2]
            await client.post(f"{API}/gateway/ack", headers=gateway2, json={"ids": ids2})
            for message_id in ids2:
                await client.post(f"{API}/gateway/report", headers=gateway2, json={"id": message_id, "status": "delivered"})
            # A few queued bulk messages so the live queue shows lanes.
            await api_call(client, "POST", "/messages", token=token, json={
                "to": contact_phones[:5], "text": "Faqat shu hafta: 20% chegirma! Batafsil: xabarchi.uz", "priority": "bulk",
            })
            step("today", "4 delivered, queue left non-empty")

            # ---- heartbeats: device liveness on the cards -------------
            await client.post(f"{API}/gateway/heartbeat", headers=gateway, json={"battery": 84, "signal": 4, "connection": "realtime", "sentToday": 12})
            await client.post(f"{API}/gateway/heartbeat", headers=gateway2, json={"battery": 41, "signal": 3, "connection": "polling", "sentToday": 4})
            # third device stays offline on purpose
            step("heartbeats", "2 online, 1 offline")

            # ---- api keys ---------------------------------------------
            await api_call(client, "POST", "/api-keys", token=token, json={"name": "Production server", "scopes": ["sms.send", "sms.read"]})
            await api_call(client, "POST", "/api-keys", token=token, json={"name": "Analitika o'quvchi", "scopes": ["sms.read", "devices.read"]})
            step("api keys", "2 created")

            # ---- telegram bot + subscribers + broadcasts --------------
            # The demo bot is a mock — it has no real BotFather token, so we
            # insert it directly instead of POST /telegram/connect (which now
            # validates the token against Telegram's getMe). token_enc stays
            # NULL, so broadcasts take the mocked-delivery path and the demo
            # stays lively without a live bot.
            bot_id = uuid.uuid4()
            await db.execute(
                """INSERT INTO telegram_bots
                       (id, user_id, username, title, status, token_hash, webhook_ok,
                        connected_at, created_at, updated_at)
                   VALUES ($1, $2, 'xabarchidemo_bot', 'Xabarchi Demo', 'active', $3, true,
                        now(), now(), now())""",
                bot_id, user_id, hashlib.sha256(b"demo-seed-bot").hexdigest(),
            )
            subscribers = [
                ("Jasur Karimov", "jasur_k", 152, "link"), ("Dilnoza R.", None, 12, "qr"),
                ("Bekzod T.", "bekzod_t", 210, "search"), ("Malika Yusupova", "malika_y", 48, "link"),
                ("Sardor A.", None, 305, "qr"), ("Nigora Islomova", "nigora_i", 88, "link"),
                ("Rustam N.", "rustam_n", 265, "link"), ("Zilola H.", None, 330, "qr"),
            ]
            for index, (name, username, hue, source) in enumerate(subscribers):
                await db.execute(
                    """INSERT INTO bot_subscribers (id, bot_id, name, username, avatar_hue, source, joined_at, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, now(), now())""",
                    uuid.uuid4(), bot_id, name, username, hue, source,
                    datetime.now(UTC) - timedelta(days=20 - index * 2),
                )
            broadcasts = [
                {"kind": "text", "text": "Assalomu alaykum! Yangi mavsum mahsulotlari keldi 🎉"},
                {"kind": "photo", "text": "Yangi kolleksiya — 20% chegirma", "mediaName": "kolleksiya.jpg"},
                {"kind": "post", "text": "Katta aksiya boshlanadi! Batafsil saytda.", "buttonLabel": "Saytga o'tish", "buttonUrl": "https://xabarchi.uz"},
            ]
            for index, broadcast in enumerate(broadcasts):
                created = await api_call(client, "POST", "/telegram/broadcasts", token=token, json=broadcast)
                await db.execute(
                    "UPDATE bot_broadcasts SET created_at=$2 WHERE id=$1",
                    created["id"], datetime.now(UTC) - timedelta(days=6 - index * 3, hours=index * 2),
                )
            step("telegram", f"bot + {len(subscribers)} subscribers + {len(broadcasts)} broadcasts")

            # ---- notifications ----------------------------------------
            notification_rows = [
                ("device", "success", {"uz": "Qurilma ulandi", "ru": "Устройство подключено", "en": "Device connected"},
                 {"uz": "Ofis — asosiy (Samsung Galaxy A54) muvaffaqiyatli ulandi.", "ru": "Ofis — asosiy (Samsung Galaxy A54) успешно подключено.", "en": "Ofis — asosiy (Samsung Galaxy A54) connected successfully."}, True, 5),
                ("sms", "info", {"uz": "Ommaviy yuborish yakunlandi", "ru": "Массовая рассылка завершена", "en": "Bulk send finished"},
                 {"uz": "25 ta xabardan 24 tasi yetkazildi.", "ru": "Доставлено 24 из 25 сообщений.", "en": "24 of 25 messages delivered."}, True, 2),
                ("device", "warn", {"uz": "Qurilma oflayn", "ru": "Устройство офлайн", "en": "Device offline"},
                 {"uz": "Zaxira telefon 3 kundan beri aloqaga chiqmadi.", "ru": "Zaxira telefon не выходит на связь 3 дня.", "en": "Zaxira telefon has been unreachable for 3 days."}, False, 1),
                ("billing", "info", {"uz": "Biznes tarifi faol", "ru": "Тариф Biznes активен", "en": "Biznes plan active"},
                 {"uz": "Oylik limit: 10 000 SMS. Xarid uchun rahmat!", "ru": "Месячный лимит: 10 000 SMS. Спасибо за покупку!", "en": "Monthly quota: 10,000 SMS. Thanks for your purchase!"}, False, 0),
            ]
            for kind, severity, title, body, read, days_back in notification_rows:
                await db.execute(
                    """INSERT INTO notifications (id, user_id, kind, severity, title, body, read, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $8)""",
                    uuid.uuid4(), user_id, kind, severity,
                    __import__("json").dumps(title), __import__("json").dumps(body), read,
                    datetime.now(UTC) - timedelta(days=days_back, hours=3),
                )
            step("notifications", str(len(notification_rows)))

            # ---- invoices (billing history) ---------------------------
            now = datetime.now(UTC)
            for months_back in (1, 0):
                date = (now.replace(day=1) - timedelta(days=months_back * 28)).replace(day=1, hour=9)
                await db.execute(
                    """INSERT INTO invoices (id, user_id, number, date, amount, status, plan_id, period, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, 'paid', 'biznes', $6, $4, $4)""",
                    uuid.uuid4(), user_id, f"INV-{date.year}-{90 + months_back:04d}", date, 149000, f"{date:%Y-%m}",
                )
            step("invoices", "2 paid")

        finally:
            await db.close()

    print("\nDemo account is ready:")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
