"""FastAPI app: receives WhatsApp webhooks and hands each message to the engine."""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.db.session import make_session_factory
from app.engine.engine import Engine
from app.engine.llm import AnthropicLLM
from app.queue import PhoneQueue
from app.routing.projects import RoutingTable
from app.settings import Settings, get_settings
from app.types import Inbound
from app.whatsapp.client import WhatsAppClient
from app.whatsapp.parse import parse_webhook
from app.whatsapp.verify import signature_valid

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def build_engine(settings: Settings, database_url: str | None = None) -> Engine:
    table = RoutingTable.load(settings.projects_file)
    reasons = json.loads(settings.reasons_file.read_text(encoding="utf-8"))
    return Engine(
        sessions=make_session_factory(database_url or settings.database_url),
        llm=AnthropicLLM(table, reasons, settings.anthropic_model, settings.anthropic_api_key),
        table=table,
        reasons=reasons,
        session_timeout_hours=settings.session_timeout_hours,
        alert_template=settings.alert_template_name,
        alert_template_lang=settings.alert_template_lang,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.engine = build_engine(settings)
    app.state.whatsapp = WhatsAppClient(
        settings.whatsapp_access_token,
        settings.whatsapp_phone_number_id,
        settings.graph_api_version,
        settings.dry_run,
    )
    app.state.queue = PhoneQueue()
    if settings.dry_run:
        log.warning("DRY_RUN is on: outgoing WhatsApp messages are printed, not sent")
    yield
    await app.state.queue.drain()
    await app.state.whatsapp.close()


app = FastAPI(title="WhatsApp intake bot", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/webhook")
async def verify_webhook(
    request: Request,
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> PlainTextResponse:
    """Meta calls this once when the webhook is registered."""
    expected = request.app.state.settings.whatsapp_verify_token
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    settings: Settings = request.app.state.settings
    raw = await request.body()
    signed = signature_valid(
        settings.whatsapp_app_secret, raw, request.headers.get("X-Hub-Signature-256")
    )
    # Unsigned payloads are accepted only for local testing: dry run with no app secret set.
    if not signed and not (settings.dry_run and not settings.whatsapp_app_secret):
        raise HTTPException(status_code=403, detail="bad signature")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    # Acknowledge straight away; Meta retries anything that isn't answered quickly.
    for inbound in parse_webhook(payload):
        request.app.state.queue.submit(inbound.phone, _job(request.app, inbound))
    return {"received": True}


def _job(app: FastAPI, inbound: Inbound):
    async def run() -> None:
        try:
            for out in await app.state.engine.handle(inbound):
                await app.state.whatsapp.send(out)
        except Exception:
            log.exception("failed to handle message from a caller")

    return run
