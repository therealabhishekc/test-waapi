import os
import requests
import asyncio
import httpx
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import json


# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("TOKEN")       # WhatsApp access token (long-lived)
VERIFY_TOKEN = os.getenv("MYTOKEN")  # Webhook verify token you chose
PORT = int(os.getenv("PORT", "8000"))
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")


# Example “hashmap” of recipients (E.164 numbers; no spaces, usually no '+')
RECIPIENTS = {
    "14694652751": {"name": "Ahishek", "address": "11 Apple St, NY", "buying_power": "Low"},
    "19453083188": {"name": "Karthik",   "address": "221B Baker St, London", "buying_power": "Medium"},
    "12142187390": {"name": "Sristy", "address": "DLF Phase 3, Gurgaon", "buying_power": "High"},
}


# Initialize FastAPI app
app = FastAPI(title="WhatsApp Webhook (Python)")


# Root endpoint
@app.get("/")
def root():
    return {"ok": True, "msg": "Yes yes it is working"}


# Webhook verification (GET /webhook)
@app.get("/webhook", response_class=PlainTextResponse)
def verify(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return hub_challenge or ""
    raise HTTPException(status_code=403, detail="Verification failed")


# Webhook receiver (POST /webhook)
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    print(json.dumps(body, indent=2))

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

    reply_text = "Unsubscribed" if msg_body.lower() == "stop" else "Subscribed"

    if phone_number_id and from_e164:
        # Build WhatsApp Cloud API call
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {TOKEN}", 
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": from_e164,
            # "type": "text",
            # "text": {"body": reply_text}
            "type": "template",
            "template": {
                "name": "junemark",  # Pre-approved template name
                "language": {"code": "en"},
                # "components": [
                #     {
                #         "type": "body",
                #         "parameters": [
                #             {
                #                 "type": "text", 
                #                 "parameter_name": "crisis", 
                #                 "text": "testing"
                #             }  
                #         ]
                #     }
                # ]
            }
        }
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            # Log error in real app
            print("Send error:", e)
            if resp is not None:
                print("Status:", resp.status_code)
                print("Graph body:", resp.text)

    return {"ok": True}


# Bulk send endpoint (GET /send-bulk)
@app.get("/send-bulk")
async def send_bulk(
    template: str = Query("junemark"),
    lang: str = Query("en"),
    dry_run: bool = Query(False, description="If true, don't send—just show payloads")
):
    """
    Send a template message to every number in RECIPIENTS.
    Template must have 3 body placeholders: {{1}} name, {{2}} address, {{3}} buying_power.
    """
    if not TOKEN:
        raise HTTPException(500, "TOKEN env var not set")
    if not PHONE_NUMBER_ID:
        raise HTTPException(500, "PHONE_NUMBER_ID env var not set")

    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = []
        send_order = []  # keep (to) aligned with responses
        results = []

        for to, info in RECIPIENTS.items():
            body_params = [
                {"type": "text", "text": str(info.get("name", ""))},
                {"type": "text", "text": str(info.get("address", ""))},
                {"type": "text", "text": str(info.get("buying_power", ""))},
            ]

            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": lang},
                    # "components": [
                    #     {"type": "body", "parameters": body_params}
                    # ],
                },
            }

            if dry_run:
                results.append({"to": to, "payload": payload})
            else:
                tasks.append(client.post(url, json=payload, headers=headers))
                send_order.append(to)

        if dry_run:
            return {"dry_run": True, "count": len(results), "results": results}

        # fire all sends concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for to, resp in zip(send_order, responses):
            if isinstance(resp, Exception):
                results.append({"to": to, "ok": False, "error": str(resp)})
            else:
                ok = 200 <= resp.status_code < 300
                results.append({
                    "to": to,
                    "ok": ok,
                    "status": resp.status_code,
                    "body": (resp.json() if ok else resp.text),
                })

    sent = sum(1 for r in results if r.get("ok"))
    return {"sent": sent, "total": len(results), "results": results}


# Run the app with Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
