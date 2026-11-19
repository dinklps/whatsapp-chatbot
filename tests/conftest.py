import json
from pathlib import Path

import pytest

from app.db.session import make_session_factory
from app.engine.engine import Engine
from app.engine.llm import Extracted, LLMError, TurnContext, TurnOutput
from app.routing.projects import RoutingTable

ROOT = Path(__file__).resolve().parent.parent


def turn(asked_slot="none", reply="", **fields) -> TurnOutput:
    """Build a model turn. Extraction fields go in as keyword arguments."""
    flags = {
        k: fields.pop(k, False) for k in ("wants_human", "start_over", "closing_remark")
    }
    language = fields.pop("language", "English")
    return TurnOutput(
        extracted=Extracted.empty().model_copy(update=fields),
        language=language,
        asked_slot=asked_slot,
        reply=reply,
        **flags,
    )


class FakeLLM:
    """Plays back scripted turns. `phrase` echoes the instruction so tests can see it was used."""

    def __init__(self):
        self.turns: list[TurnOutput | Exception] = []
        self.contexts: list[TurnContext] = []
        self.phrase_fails = False

    def script(self, *turns):
        self.turns.extend(turns)

    async def turn(self, ctx: TurnContext) -> TurnOutput:
        self.contexts.append(ctx)
        item = self.turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def phrase(self, instruction: str, language: str) -> str:
        if self.phrase_fails:
            raise LLMError("down")
        if "exactly one question" in instruction:
            return f"PHRASED {instruction.split('.')[0]}?"
        return f"PHRASED {instruction.split('.')[0]}."


@pytest.fixture
def table() -> RoutingTable:
    return RoutingTable.load(ROOT / "config" / "projects.json")


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def engine(llm, table) -> Engine:
    reasons = json.loads((ROOT / "config" / "reasons.json").read_text(encoding="utf-8"))
    return Engine(
        sessions=make_session_factory("sqlite://"),
        llm=llm,
        table=table,
        reasons=reasons,
    )
