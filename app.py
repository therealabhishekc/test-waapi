import os
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")       # WhatsApp access token (long-lived)
VERIFY_TOKEN = os.getenv("MYTOKEN")  # Webhook verify token you chose
PORT = int(os.getenv("PORT", "8000"))

app = FastAPI(title="WhatsApp Webhook (Python)")

@app.get("/")
def root():
    return {"ok": True, "msg": "Yes yes it is working"}

# Webhook verification (GET /webhook)
@app.get("/webhook", response_class=PlainTextResponse)
def verify(mode: str | None = None, hub_challenge: str | None = None, hub_verify_token: str | None = None, **qs):
    # Meta sends these as query params: hub.mode / hub.challenge / hub.verify_token
    mode = qs.get("hub.mode", mode)
    challenge = qs.get("hub.challenge", hub_challenge)
    token = qs.get("hub.verify_token", hub_verify_token)

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge or ""
    raise HTTPException(status_code=403, detail="Verification failed")

# Webhook receiver (POST /webhook)
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    # print nicely if you want:
    # import json; print(json.dumps(body, indent=2))

    try:
        changes = body.get("entry", [])[0].get("changes", [])[0].get("value", {})
    except Exception:
        # structure didn't match
        return {"ok": True}

    # Check for inbound messages
    messages = changes.get("messages")
    if not messages:
        return {"ok": True}  # could be statuses or other notifications

    msg = messages[0]
    metadata = changes.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    from_e164 = msg.get("from")

    # Text body if present
    msg_body = (msg.get("text") or {}).get("body", "")

    if phone_number_id and from_e164:
        # Build WhatsApp Cloud API call
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        data = {
            "messaging_product": "whatsapp",
            "to": from_e164,
            "text": {"body": "Hi, im aski"}  # your reply text
        }
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            # Log error in real app
            print("Send error:", e)

    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
