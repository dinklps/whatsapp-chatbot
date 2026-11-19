"""Sends messages through the WhatsApp Cloud API (or prints them in dry-run mode)."""

import logging

import httpx

from app.types import Outbound

log = logging.getLogger(__name__)


def to_payload(out: Outbound) -> dict:
    payload: dict = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": out.to}
    if out.kind == "list":
        payload["type"] = "interactive"
        payload["interactive"] = {
            "type": "list",
            "body": {"text": out.body[:1024]},
            "action": {
                "button": out.button[:20],
                "sections": [
                    {
                        "title": "Options",
                        "rows": [{"id": rid, "title": title[:24]} for rid, title in out.rows],
                    }
                ],
            },
        }
    elif out.kind == "template":
        payload["type"] = "template"
        payload["template"] = {
            "name": out.template,
            "language": {"code": out.template_lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in out.params]}
            ],
        }
    else:
        payload["type"] = "text"
        payload["text"] = {"body": out.body[:4096], "preview_url": False}
    return payload


class WhatsAppClient:
    def __init__(self, access_token: str, phone_number_id: str, api_version: str, dry_run: bool):
        self.dry_run = dry_run
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {access_token}"}, timeout=20.0
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def send(self, out: Outbound) -> bool:
        if self.dry_run:
            print(f"\n--- DRY RUN: {out.kind} to {out.to} ({out.purpose}) ---\n{out.body}")
            for _, title in out.rows:
                print(f"  [ {title} ]")
            return True
        if await self._post(to_payload(out)):
            return True
        if out.kind == "template":
            # Template missing or not yet approved. Plain text still reaches a staff member who
            # has messaged the bot's number within the last 24 hours.
            log.error("template '%s' failed for %s; trying plain text", out.template, out.to)
            return await self._post(to_payload(Outbound(to=out.to, body=out.body)))
        return False

    async def _post(self, payload: dict) -> bool:
        try:
            response = await self.http.post(self.url, json=payload)
        except httpx.HTTPError as e:
            log.error("WhatsApp send failed: %s", e)
            return False
        if response.status_code >= 400:
            log.error("WhatsApp send rejected (%s): %s", response.status_code, response.text[:500])
            return False
        return True
