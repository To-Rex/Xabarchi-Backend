"""End-to-end smoke test against a running server + real DB.

Run:  .venv/Scripts/python.exe tests/smoke_e2e.py
Walks the full lifecycle: register -> me -> pair device -> send SMS
(priority) -> gateway claim/ack/report -> list -> analytics -> websocket.
"""

import asyncio
import json
import secrets
import sys

import httpx
import websockets

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"


def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


async def main() -> None:
    email = f"smoke_{secrets.token_hex(4)}@xabarchi.uz"
    async with httpx.AsyncClient(timeout=30) as client:
        # register
        r = await client.post(f"{API}/auth/register", json={
            "firstName": "Smoke", "lastName": "Test", "email": email,
            "password": "smoke1234", "company": "Smoke Express", "phone": "998901112233",
        })
        step("register", r.status_code == 201, f"{r.status_code}")
        tokens = r.json()
        headers = {"Authorization": f"Bearer {tokens['accessToken']}"}

        # me
        r = await client.get(f"{API}/auth/me", headers=headers)
        step("me", r.status_code == 200 and r.json()["email"] == email)

        # pair device
        r = await client.post(f"{API}/devices/pair", headers=headers, json={
            "name": "Smoke ofis", "model": "Pixel 6a", "phone": "998901112233",
            "operator": "Ucell", "androidVersion": "15", "appVersion": "2.4.1", "dailyLimit": 500,
        })
        step("device pair", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")
        pair = r.json()
        device_token = pair["token"]
        device_id = pair["device"]["id"]
        dev_headers = {"X-Device-Token": device_token}

        # send urgent + bulk SMS
        r = await client.post(f"{API}/messages", headers=headers, json={
            "to": ["+998901234567"], "text": "Tasdiqlash kodingiz: 48213", "priority": "urgent", "deviceId": device_id,
        })
        step("send urgent", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")
        r = await client.post(f"{API}/messages", headers=headers, json={
            "to": ["+998935557713", "+998917822440"], "text": "Chegirma boshlandi!", "priority": "bulk",
        })
        step("send bulk x2", r.status_code in (200, 201))

        # websocket: subscribe before gateway acts, expect message.updated
        ws_events = []

        async def listen():
            uri = f"ws://127.0.0.1:8000/api/v1/ws?token={tokens['accessToken']}"
            async with websockets.connect(uri) as ws:
                try:
                    while len(ws_events) < 1:
                        raw = await asyncio.wait_for(ws.recv(), timeout=15)
                        ws_events.append(json.loads(raw))
                except (asyncio.TimeoutError, TimeoutError):
                    pass

        listener = asyncio.create_task(listen())
        await asyncio.sleep(1.0)

        # gateway claim — urgent must come first
        r = await client.post(f"{API}/gateway/claim", headers=dev_headers, json={"limit": 10})
        step("gateway claim", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        claimed = r.json()
        step("claim count == 3", len(claimed) == 3, str(len(claimed)))
        step("priority FIFO (urgent first)", claimed[0]["priority"] == "urgent", claimed[0]["priority"])

        ids = [m["id"] for m in claimed]
        r = await client.post(f"{API}/gateway/ack", headers=dev_headers, json={"ids": ids})
        step("gateway ack", r.status_code == 200)

        r = await client.post(f"{API}/gateway/report", headers=dev_headers, json={"id": ids[0], "status": "delivered"})
        step("gateway report delivered", r.status_code == 200)

        # heartbeat
        r = await client.post(f"{API}/gateway/heartbeat", headers=dev_headers, json={
            "battery": 88, "signal": 4, "connection": "realtime",
        })
        step("gateway heartbeat", r.status_code == 200)

        # list messages
        r = await client.get(f"{API}/messages", headers=headers, params={"page": 1, "pageSize": 10})
        body = r.json()
        step("list messages", r.status_code == 200 and body["total"] == 3, f"total={body.get('total')}")

        # analytics
        r = await client.get(f"{API}/analytics/overview", headers=headers)
        step("analytics overview", r.status_code == 200, r.text[:120])

        # api key create + public send
        r = await client.post(f"{API}/api-keys", headers=headers, json={"name": "Smoke key", "scopes": ["sms.send"]})
        step("api key create", r.status_code in (200, 201), f"{r.status_code} {r.text[:160]}")
        full_key = r.json()["key"]
        r = await client.post(f"{API}/public/messages", headers={"X-API-Key": full_key}, json={
            "to": ["+998909998877"], "text": "API orqali salom", "priority": "transactional",
        })
        step("public send via API key", r.status_code in (200, 201), f"{r.status_code} {r.text[:160]}")

        await listener
        step("websocket received event", len(ws_events) >= 1, ws_events[0]["event"] if ws_events else "none")

        # ---- QR pairing flow (fresh user so the Start-plan cap is free) ----
        email2 = f"smoke_qr_{secrets.token_hex(4)}@xabarchi.uz"
        r = await client.post(f"{API}/auth/register", json={
            "firstName": "Qr", "lastName": "Smoke", "email": email2,
            "password": "smoke1234", "company": "QR Express", "phone": "998905556677",
        })
        headers2 = {"Authorization": f"Bearer {r.json()['accessToken']}"}

        r = await client.post(f"{API}/devices/pair/start", headers=headers2)
        step("qr pair/start", r.status_code == 200, r.text[:120])
        pair_code = r.json()["code"]
        step("qr payload deep link", r.json()["qrPayload"].startswith("xabarchi://pair?code="))

        # phone side: no auth header, just the scanned code
        device_body = {
            "code": pair_code, "name": "QR telefon", "model": "Galaxy A54",
            "phone": "998905556677", "operator": "Beeline",
            "androidVersion": "14", "appVersion": "2.4.1", "dailyLimit": 400,
        }
        r = await client.post(f"{API}/devices/pair/complete", json=device_body)
        step("qr pair/complete", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        qr_token = r.json()["token"]
        step("qr device token minted", qr_token.startswith("xab_device_"))

        # code is strictly one-time
        r = await client.post(f"{API}/devices/pair/complete", json=device_body)
        step("qr code one-time (reuse 401)", r.status_code == 401, str(r.status_code))

        # Start plan allows 1 device: a second pairing must hit the quota
        r = await client.post(f"{API}/devices/pair/start", headers=headers2)
        r = await client.post(f"{API}/devices/pair/complete", json={**device_body, "code": r.json()["code"]})
        step("plan device cap (402)", r.status_code == 402, str(r.status_code))

        # the QR-paired token works for gateway calls
        r = await client.post(f"{API}/gateway/heartbeat", headers={"X-Device-Token": qr_token}, json={
            "battery": 77, "signal": 3, "connection": "realtime",
        })
        step("qr token heartbeat", r.status_code == 200)

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
