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

# 5. Server (dev, hot-reload)
uvicorn app.main:app --reload --port 8000

# yoki production kabi: migratsiyalarni qo'llab, .env'dagi PORT bilan
python -m app
```

Swagger UI: <http://localhost:8000/docs> · Health: `GET /healthz` · Readiness: `GET /readyz`

Testlar: `pytest tests/` (infra talab qilmaydi — smoke test DB/Redis'siz o'tadi).

## Deploy (Dokploy / Railpack)

Repo ildizidagi [`railpack.json`](railpack.json) Dokploy'ga buildni Railpack
bilan qilishni aytadi: Python 3.12, `requirements.txt` o'rnatiladi, start
komandasi — `python -m app`. Bu komanda:

1. avval `alembic upgrade head` ni bajaradi (yangi migratsiya bo'lsa qo'llaydi,
   xato bo'lsa nolga teng bo'lmagan kod bilan chiqadi — deploy fail bo'ladi);
2. keyin serverni `0.0.0.0:{PORT}` da ko'taradi (`PORT` env/.env'dan, default 8000).

Dokploy'da qilinadigan ishlar:

- Environment bo'limiga `.env`dagi barcha qiymatlarni kiriting (`DATABASE_URL`,
  `REDIS_URL`, `JWT_SECRET`, `PORT`, `CORS_ORIGINS` — production frontend
  domenini ham qo'shing, `FRONTEND_URL`, `PUBLIC_API_URL` va h.k.).
- Health check: `GET /healthz` (liveness) yoki `GET /readyz` (DB+Redis bilan).
- Git push → avtomatik deploy. Docker bilan deploy qilinsa ham xuddi shu
  `python -m app` ishlaydi (Dockerfile saqlangan).

## .env

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` da log darajasi INFO bo'ladi |
| `PORT` | `8000` | `python -m app` / deploy shu portda ishlaydi |
| `DATABASE_URL` | — (majburiy) | `postgresql://...` — asyncpg dialektiga avtomatik o'giriladi |
| `REDIS_URL` | — (majburiy) | pub/sub va rate limiting uchun |
| `JWT_SECRET` | — (majburiy) | HS256 imzo kaliti (64+ tasodifiy belgi) |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_TTL_MINUTES` | `30` | access token muddati |
| `REFRESH_TOKEN_TTL_DAYS` | `30` | refresh token muddati |
| `CORS_ORIGINS` | `http://localhost:5173` | vergul bilan ajratilgan ro'yxat |
| `GATEWAY_LEASE_SECONDS` | `120` | device claim lease muddati |
| `GATEWAY_CLAIM_MAX` | `100` | bitta claim'dagi maksimal xabarlar soni |
| `FRONTEND_URL` | `http://localhost:5173` | e-mail havolalari, OAuth va checkout redirectlari |
| `PUBLIC_API_URL` | `http://localhost:8000` | OAuth callback va Telegram webhook URL'ini qurishda. Telegram obunachilari uchun **ochiq HTTPS** bo'lishi shart (aks holda webhook o'rnatilmaydi, bot ulanadi-yu obunachi kelmaydi) |
| `GOOGLE_CLIENT_ID/SECRET`, `APPLE_CLIENT_ID/SECRET` | bo'sh | social auth (bo'sh — o'chik) |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | bo'sh | bo'sh bo'lsa xatlar logga yoziladi (dev) |
| `POLAR_ACCESS_TOKEN`, `POLAR_WEBHOOK_SECRET` | bo'sh | Polar billing (bo'sh — o'chik) |
| `POLAR_SERVER` | `sandbox` | `sandbox` / `production` |
| `POLAR_PRODUCT_BIZNES`, `POLAR_PRODUCT_KORXONA` | bo'sh | tarif → Polar product xaritasi |

## Endpoints

Hammasi `/api/v1` prefiksi ostida (probe'lardan tashqari).

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/register` | — | Ro'yxatdan o'tish (201, token pair + user) |
| POST | `/auth/login` | — | Kirish (token pair + user) |
| POST | `/auth/refresh` | — | Refresh token bilan yangi pair |
| GET/PATCH | `/auth/me` | JWT | Profil / profilni yangilash |
| POST | `/auth/password/forgot` | — | Parol tiklash havolasini yuborish (email mavjudligini oshkor qilmaydi) |
| POST | `/auth/password/reset` | — | Bir martalik token bilan yangi parol o'rnatish |
| POST | `/auth/email/verify` | — | E-mail tasdiqlash (bir martalik token) |
| POST | `/auth/email/resend` | JWT | Tasdiqlash xatini qayta yuborish |
| GET | `/auth/oauth/{provider}/start` | — | Google/Apple konsent sahifasiga 302 |
| GET/POST | `/auth/oauth/{provider}/callback` | — | OAuth callback → frontendga token fragment bilan 302 |
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
| POST | `/telegram/connect` | JWT | BotFather token bilan ulash (token `getMe` orqali tekshiriladi, shifrlangan holda saqlanadi, webhook o'rnatiladi) |
| DELETE | `/telegram/bot` | JWT | Uzish (webhook o'chiriladi, soft delete) |
| GET | `/telegram/subscribers`, `/telegram/broadcasts` | JWT | Obunachilar / tarixiy broadcastlar |
| POST | `/telegram/broadcasts` | JWT | Broadcast — har bir obunachiga haqiqiy `sendMessage` |
| POST | `/telegram/webhook/{secret}` | Sekret | Telegram update'lari (ochiq; `/start` yuborgan obunachini ro'yxatga oladi) |
| GET | `/notifications`, `/notifications/unread-count` | JWT | Bildirishnomalar |
| POST | `/notifications/{id}/read`, `/notifications/read-all` | JWT | O'qildi deb belgilash |
| GET | `/analytics/overview`, `/analytics/daily` | JWT | Dashboard statistikasi |
| GET/POST/DELETE | `/api-keys` | JWT | API kalitlar (kalit **bir marta** ko'rsatiladi) |
| GET | `/billing/plans`, `/billing/invoices` | JWT* | Tariflar (ochiq) va hisob-fakturalar |
| POST | `/billing/checkout` | JWT | Polar checkout sessiyasi — `{url}` qaytaradi |
| GET | `/billing/portal` | JWT | Polar customer-portal havolasi (obunani boshqarish) |
| POST | `/billing/webhook/polar` | Webhook imzo | Polar eventlari (order.paid, subscription.*) |
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

## Social auth, parol tiklash, e-mail tasdiqlash

**Social sign-in (Google / Apple).** Backend butun OAuth redirect oqimini o'zi boshqaradi:
`GET /auth/oauth/{provider}/start` → provayder konsenti → callback → foydalanuvchi
topiladi/yaratiladi → brauzer `{FRONTEND_URL}/auth/callback#accessToken=...&refreshToken=...`
ga 302 qilinadi (tokenlar URL fragmentida — server loglariga tushmaydi; xatolar
`#error=<code>` bilan qaytadi). Provayder faqat client id sozlanganda yoqiladi
(`GOOGLE_CLIENT_ID`, `APPLE_CLIENT_ID`); provayder tasdiqlagan e-mail avtomatik
tasdiqlangan sanaladi. Social-only akkauntlarda parol yo'q (`password_hash IS NULL`).

**Parol tiklash.** `POST /auth/password/forgot {email}` har doim 200 qaytaradi
(e-mail mavjudligini oshkor qilmaydi); mavjud bo'lsa Redis'da 30 daqiqalik bir
martalik token yaratilib, `{FRONTEND_URL}/reset-password?token=...` havolasi
yuboriladi. `POST /auth/password/reset {token, password}` — token `GETDEL` bilan
qat'iy bir martalik.

**E-mail tasdiqlash.** Ro'yxatdan o'tishda 24 soatlik token bilan tasdiqlash
havolasi yuboriladi (`{FRONTEND_URL}/verify-email?token=...`);
`POST /auth/email/verify {token}` tasdiqlaydi, `POST /auth/email/resend` (JWT)
qayta yuboradi. `UserOut`da `emailVerified` maydoni bor.

**SMTP.** `SMTP_HOST` bo'sh bo'lsa xatlar yuborilmaydi, havola server logiga
yoziladi (dev-rejim) — oqimlar mail-serversiz ham sinovdan o'tadi.

## To'lovlar — Polar (polar.sh)

Pullik tariflar Polar orqali sotiladi. Sozlash: `POLAR_ACCESS_TOKEN` (OAT),
`POLAR_WEBHOOK_SECRET`, `POLAR_SERVER` (`sandbox`/`production`) va tarif → Polar
mahsulot xaritasi `POLAR_PRODUCT_BIZNES` / `POLAR_PRODUCT_KORXONA`.

1. **Checkout**: dashboard `POST /billing/checkout {"planId": "biznes"}` chaqiradi →
   backend Polar'da checkout sessiya yaratadi (`external_customer_id` va
   `metadata.user_id` — bizning user id) va hosted `{url}` qaytaradi; frontend
   brauzerni shu URLga yo'naltiradi. Muvaffaqiyatda mijoz
   `{FRONTEND_URL}/app/billing?checkout=success` ga qaytadi.
2. **Webhook** (`POST /billing/webhook/polar`, Standard Webhooks imzosi bilan):
   - `order.paid` → invoice yoziladi (order id bo'yicha **idempotent** — takroriy
     yetkazish dublikat yaratmaydi), tarif faollashtiriladi, `plan_expires_at`
     yangilanadi va oylik kvota (`sms_sent_this_month`) nolga tushadi + bildirishnoma;
   - `subscription.active` → tarifni (qayta) faollashtiradi va muddatni uzaytiradi;
   - `subscription.revoked` → hisob Start'ga qaytariladi, `plan_expires_at=NULL` (bloklanadi).
3. **Customer portal**: `GET /billing/portal` → Polar'ning hosted portal havolasi
   (obunani bekor qilish, karta almashtirish o'sha yerda).

**Amaldagi tarif (bepul tier + muddat).** Bepul `start` tarifi doim o'z limiti
doirasida ishlaydi (1 qurilma, 500 SMS/oy). Pullik tariflar (`biznes`/`korxona`)
obuna **faol** bo'lganda kattaroq limitlarni ochadi; muddat tugagach hisob
**bloklanmaydi**, balki `start` (bepul) limitlariga tushadi — yangilaguncha.
Shu sababli barcha kvota tekshiruvlari (SMS yuborish, qurilma ulash, analitika)
`subscription_service.effective_plan_id(user)` — ya'ni obuna faol bo'lsa o'sha
tarif, aks holda `start` — orqali hisoblanadi (har so'rovda, cron shart emas).
"Faol" degani: `plan_id` `biznes`/`korxona` **va** `plan_expires_at` kelajakda.
`/auth/me` javobida `planActive` va `planExpiresAt` bor.

Webhook imzosi qo'lda tekshiriladi (HMAC-SHA256, `webhook-id.webhook-timestamp.body`,
5 daqiqa tolerans) — `POLAR_ACCESS_TOKEN` bo'sh bo'lsa butun integratsiya 503
`billing_not_configured` bilan o'chik turadi.

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
