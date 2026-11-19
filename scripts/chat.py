"""Talk to the bot in the terminal, without WhatsApp.

    python -m scripts.chat                    # as a new caller
    python -m scripts.chat --phone 60123456789

Uses the real model (needs ANTHROPIC_API_KEY) and a separate database, data/chat.db.
Type /voice to simulate sending a voice note, /quit to exit.
"""

import argparse
import asyncio
import logging
import sys

from app.main import build_engine
from app.settings import get_settings
from app.types import Inbound


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone", default="60111111111", help="caller's number (digits only)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    for stream in (sys.stdout, sys.stdin):
        stream.reconfigure(encoding="utf-8")
    engine = build_engine(get_settings(), database_url="sqlite:///./data/chat.db")
    print(f"Chatting as {args.phone}. /voice sends a voice note, /quit exits.\n")

    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text == "/quit":
            break
        if not text:
            continue
        inbound = (
            Inbound(phone=args.phone, text="", kind="audio")
            if text == "/voice"
            else Inbound(phone=args.phone, text=text)
        )
        for out in await engine.handle(inbound):
            if out.purpose == "alert":
                print(f"\n[ALERT to staff {out.to}]\n{out.body}\n")
            else:
                print(f"bot> {out.body}")
                for _, title in out.rows:
                    print(f"       [ {title} ]")


if __name__ == "__main__":
    asyncio.run(main())
