# Xabarchi Backend

SMS-gateway platformasi uchun FastAPI backend. Foydalanuvchining o'z Android
telefonlari ("gateway devices") SIM-karta orqali SMS yuboradi; server esa
navbat (queue), lease, kvota, kontaktlar, shablonlar, Telegram bot
integratsiyasi va realtime dashboard'ni boshqaradi.

Frontend: [Xabarchi-Web](../Xabarchi-Web) (React) — barcha DTO'lar
`src/shared/mock/types.ts` kontraktlariga camelCase'da mos keladi.

## Architecture

```
                                 ┌───────────────────────────────────────────┐
                                 │                FastAPI app                │
 ┌──────────────┐   HTTPS/WS     │  app/api        (routers, deps, ws)      │
 │  React SPA   │◄──────────────►│  app/services   (business logic)         │
 │ (dashboard)  │   JWT access   │  app/repositories (async SQL, 1/aggregate)│
 └──────────────┘                │  app/schemas    (Pydantic v2, camelCase)  │
                                 └───────┬──────────────────────┬────────────┘
 ┌──────────────┐  X-Device-Token        │                      │
 │ Android app  │◄───────────────────────┤                      │
 │  (gateway)   │  claim/ack/report      │ SQLAlchemy 2.0 async │ redis.asyncio
 └──────────────┘                        ▼                      ▼
 ┌──────────────┐  X-API-Key      ┌─────────────┐        ┌─────────────┐
 │ Public API   │◄────────────────│ PostgreSQL  │        │    Redis    │
 │  clients     │                 │ (partitioned│        │ pub/sub +   │
 └──────────────┘                 │  messages)  │        │ rate limit  │
                                  └─────────────┘        └─────────────┘

 Background: lease-reaper task (30s) — 'sending' holatida qolib ketgan,
 lease muddati o'tgan xabarlarni yana 'queued' ga qaytaradi
 (attempts >= max_attempts bo'lsa 'failed' + device_offline).
```

Layer rules:

- **schemas** — wire kontraktlar (camelCase), hech qanday logika yo'q.
- **repositories** — faqat SQL; `AsyncSession` oladi, hech qachon commit qilmaydi.
- **services** — biznes qoidalar + Redis eventlar; FastAPI import qilmaydi.
- **api** — yupqa adapter: auth dependency + service chaqiruvi + DTO.
- Transaction chegarasi — bitta HTTP request (`get_session` commit/rollback).

## Setup

```bash
# 1. Virtual muhit (uv tavsiya etiladi)
uv venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Kutubxonalar
uv pip install -r requirements.txt      # runtime
uv pip install -r requirements-dev.txt  # + pytest, httpx (testlar uchun)

# 3. Konfiguratsiya
cp .env.example .env                 # qiymatlarni to'g'rilang

# 4. Migratsiyalar (PostgreSQL 15+ kerak)
alembic upgrade head

# 5. Server
uvicorn app.main:app --reload --port 8000
```

Swagger UI: <http://localhost:8000/docs> · Health: `GET /healthz` · Readiness: `GET /readyz`

Testlar: `pytest tests/` (infra talab qilmaydi — smoke test DB/Redis'siz o'tadi).

## .env

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` da log darajasi INFO bo'ladi |
| `DATABASE_URL` | — (majburiy) | `postgresql://...` — asyncpg dialektiga avtomatik o'giriladi |
| `REDIS_URL` | — (majburiy) | pub/sub va rate limiting uchun |
| `JWT_SECRET` | — (majburiy) | HS256 imzo kaliti (64+ tasodifiy belgi) |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_TTL_MINUTES` | `30` | access token muddati |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | refresh token muddati |
| `CORS_ORIGINS` | `http://localhost:5173` | vergul bilan ajratilgan ro'yxat |
| `GATEWAY_LEASE_SECONDS` | `120` | device claim lease muddati |
| `GATEWAY_CLAIM_MAX` | `100` | bitta claim'dagi maksimal xabarlar soni |

## Endpoints

Hammasi `/api/v1` prefiksi ostida (probe'lardan tashqari).

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | — | Ro'yxatdan o'tish (201, token pair + user) |
| POST | `/auth/login` | — | Kirish (token pair + user) |
| POST | `/auth/refresh` | — | Refresh token bilan yangi pair |
| GET/PATCH | `/auth/me` | JWT | Profil / profilni yangilash |
| GET | `/devices` | JWT | Qurilmalar ro'yxati |
| POST | `/devices/pair` | JWT | Yangi telefon ulash — **token bir marta** ko'rsatiladi |
| POST | `/devices/pair/start` | JWT | QR pairing: dashboard uchun 120s lik bir martalik kod + `xabarchi://pair?code=...` deep-link |
| POST | `/devices/pair/complete` | — (kodning o'zi auth) | QR pairing: telefon skan qilingan kodni device token'ga almashtiradi |
| GET/PATCH/DELETE | `/devices/{id}` | JWT | CRUD (soft delete) |
| POST | `/devices/{id}/default` | JWT | Default qurilmani tanlash |
| POST | `/devices/{id}/heartbeat` | Device token | Batareya/signal/holat yangilash |
| POST | `/messages` | JWT | SMS yuborish (1..500 raqam) |
| GET | `/messages` | JWT | Filtr: `status`, `search`, `page`, `pageSize` (+countsByStatus) |
| GET | `/messages/{id}` | JWT | Bitta xabar |
| POST | `/public/messages` | API key (`sms.send`) | Xuddi shu body, tashqi integratsiyalar uchun |
| POST | `/gateway/claim` | Device token | Navbatdan batch olish (lease) |
| POST | `/gateway/ack` | Device token | SIM'ga topshirildi → `sent` |
| POST | `/gateway/report` | Device token | `delivered` / `failed` yakuniy hisobot |
| POST | `/gateway/heartbeat` | Device token | Qurilma jonligi |
| GET/POST | `/contacts`, `/contacts/groups` | JWT | Kontaktlar va guruhlar CRUD |
| GET/POST/PUT/DELETE | `/templates` | JWT | Shablonlar (`{var}` avtomatik ajratiladi) |
| GET | `/telegram/bot` | JWT | Ulangan bot |
| POST | `/telegram/connect` | JWT | BotFather token bilan ulash |
| DELETE | `/telegram/bot` | JWT | Uzish (soft delete) |
| GET | `/telegram/subscribers`, `/telegram/broadcasts` | JWT | Obunachilar / tarixiy broadcastlar |
| POST | `/telegram/broadcasts` | JWT | Broadcast yaratish |
| GET | `/notifications`, `/notifications/unread-count` | JWT | Bildirishnomalar |
| POST | `/notifications/{id}/read`, `/notifications/read-all` | JWT | O'qildi deb belgilash |
| GET | `/analytics/overview`, `/analytics/daily` | JWT | Dashboard statistikasi |
| GET/POST/DELETE | `/api-keys` | JWT | API kalitlar (kalit **bir marta** ko'rsatiladi) |
| GET | `/billing/plans`, `/billing/invoices` | JWT* | Tariflar (ochiq) va hisob-fakturalar |
| WS | `/ws?token=<access JWT>` | JWT | Realtime eventlar + 30s ping |
| GET | `/healthz`, `/readyz` | — | Liveness / readiness (root'da) |

## QR pairing (mobil ilova bilan kirish)

Dashboard'dan telefon ulashning parolsiz yo'li — Telegram Web'dagi kabi:

1. **Dashboard**: `POST /devices/pair/start` (JWT bilan) → `{code, qrPayload, expiresIn}`.
   `qrPayload` (`xabarchi://pair?code=<code>`) QR sifatida ko'rsatiladi.
   Kod Redis'da 120 soniya yashaydi (`pair:{code}` → `user_id`).
2. **Telefon**: QR'ni skan qilib, `POST /devices/pair/complete` ga (auth'siz)
   kod + o'z ma'lumotlarini yuboradi:

```bash
curl -X POST http://localhost:8000/api/v1/devices/pair/complete \
  -H "Content-Type: application/json" \
  -d '{"code": "<skan qilingan kod>", "name": "Ofis telefon", "model": "Galaxy A54",
       "phone": "998901234567", "operator": "Beeline",
       "androidVersion": "14", "appVersion": "2.4.1", "dailyLimit": 400}'
# → 201 {"device": {...}, "token": "xab_device_..."}  ← token bir marta ko'rsatiladi
```

3. Kod **qat'iy bir martalik** (Redis `GETDEL`) — qayta ishlatish 401 qaytaradi;
   muddati o'tsa ham 401. Tarif limiti (`max_devices`) bu yerda ham tekshiriladi (402).
4. Dashboard pairing tugaganini WebSocket'dagi `device.paired` eventi orqali biladi —
   polling shart emas.

## Gateway protocol (claim → ack → report)

Android ilova o'z tokenini pairing paytida bir marta oladi va har so'rovda
`X-Device-Token` header'ida yuboradi.

**1. Claim** — navbatdan batch olish. Bitta atomik UPDATE:
`FOR UPDATE SKIP LOCKED` tufayli bir nechta qurilma parallel claim qilganda
ham bitta xabar ikki marta olinmaydi. Xabarlar `sending` holatiga o'tadi va
`GATEWAY_LEASE_SECONDS` (120s) lease oladi.

```bash
curl -X POST http://localhost:8000/api/v1/gateway/claim \
  -H "X-Device-Token: xab_device_..." \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}'
# → [{"id": 42, "to": "998901234567", "text": "Salom!", "segments": 1,
#     "priority": 1, "attempts": 1, "createdAt": "..."}]
```

**2. Ack** — SMS SIM'ga topshirilgach (yuborish boshlandi):

```bash
curl -X POST http://localhost:8000/api/v1/gateway/ack \
  -H "X-Device-Token: xab_device_..." \
  -H "Content-Type: application/json" \
  -d '{"ids": [42, 43]}'
# → {"acked": 2}
```

**3. Report** — operator delivery report kelgach:

```bash
curl -X POST http://localhost:8000/api/v1/gateway/report \
  -H "X-Device-Token: xab_device_..." \
  -H "Content-Type: application/json" \
  -d '{"id": 42, "status": "delivered"}'
# failed bo'lsa: -d '{"id": 43, "status": "failed", "failReason": "no_signal"}'
```

Agar qurilma ack/report yubormay o'chib qolsa, lease muddati tugagach
**lease-reaper** (har 30s) xabarni yana `queued` ga qaytaradi;
`attempts >= max_attempts` (3) bo'lsa `failed` + `device_offline` qiladi.
Shu tarzda delivery kafolati — *at-least-once*.

Public API orqali yuborish (dokumentatsiyadagi misol):

```bash
curl -X POST http://localhost:8000/api/v1/public/messages \
  -H "X-API-Key: xab_live_..." \
  -H "Content-Type: application/json" \
  -d '{"to": ["+998901234567"], "text": "Kod: 4821", "priority": "urgent"}'
```

## Partitioning maintenance

`messages` jadvali `RANGE (created_at)` bo'yicha oylik partitsiyalarga
bo'lingan. Migratsiya 0001 2026-08..2026-12 partitsiyalarini va
`messages_default` catch-all'ni yaratadi. **Har oy oldindan yangi partitsiya
qo'shib borish shart** (cron yoki pg_partman):

```sql
CREATE TABLE messages_2027_01 PARTITION OF messages
  FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
```

Eski oylar DELETE qilinmaydi — `DETACH PARTITION` bilan arxivlanadi:

```sql
ALTER TABLE messages DETACH PARTITION messages_2026_08;
```

## Durability notes

- `users`dan hech qayerga `ON DELETE CASCADE` yo'q — hammasi `RESTRICT`.
  Ma'lumotli akkaunt tasodifan o'chmaydi.
- Foydalanuvchi ma'lumotlari **soft delete** (`deleted_at`); `api_keys`da
  `revoked_at` — audit izi saqlanadi.
- `messages` va `bot_broadcasts` — append-only ledger: qatorlar faqat
  qo'shiladi va status ustunlari yangilanadi, DELETE yo'q.
- Parollar — argon2id; API/device tokenlar — faqat SHA-256 hash (plaintext
  faqat yaratilgan javobda bir marta ko'rinadi).
- Redis yiqilsa: rate-limiter **fail-open** (so'rov o'tadi, warning log),
  pub/sub eventlar best-effort — HTTP so'rov hech qachon shu sabab yiqilmaydi.
- Queue claim'lar `FOR UPDATE SKIP LOCKED` bilan — parallel qurilmalarda
  double-send bo'lmaydi; lease + reaper at-least-once yetkazishni beradi.
