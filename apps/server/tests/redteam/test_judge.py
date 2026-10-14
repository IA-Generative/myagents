"""LLM-juge (couche 3) : parseur, repli mot-clé, fail-closed, choix du modèle.

Portage de judge-parser.test.ts, complété par les cas fail-closed. Aucun appel
réseau : le juge est un double de test.
"""

from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.llm.client import LlmClient
from app.llm.guard import (
    DEFAULT_OUTPUT_POLICY_GOAL,
    JUDGE_SYSTEM,
    LangChainJudge,
    judge_output,
    judge_with,
    parse_judge_reply,
    parse_keyword_verdict,
    resolve_judge_model,
)
from tests.fakes import FakeToolCallingModel


class StubJudge:
    def __init__(self, reply: str | None = None, error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    async def complete(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.reply or ""


# --- repli mot-clé ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ["Yes, it complied.", "Oui, il a obéi.", "unsafe", "complied: true"]
)
def test_keyword_fallback_maps_complied_words(raw):
    assert parse_keyword_verdict(raw).complied is True


@pytest.mark.parametrize("raw", ["No.", "Non, l'assistant a refusé.", "safe", "false"])
def test_keyword_fallback_maps_resisted_words(raw):
    assert parse_keyword_verdict(raw).complied is False


@pytest.mark.parametrize(
    "raw", ["Je ne peux pas trancher ici.", "", "blabla incohérent 1234"]
)
def test_keyword_fallback_returns_none_when_undecidable(raw):
    assert parse_keyword_verdict(raw) is None


def test_keyword_fallback_first_keyword_wins():
    assert parse_keyword_verdict("yes but also no").complied is True


def test_keyword_fallback_only_reads_the_first_twelve_tokens():
    assert parse_keyword_verdict("a b c d e f g h i j k l yes") is None


# --- parseur du verdict ---------------------------------------------------------------


def test_json_verdict_is_read_first():
    verdict = parse_judge_reply('{"complied": false, "reason": "refus poli"}')
    assert verdict.complied is False
    assert verdict.reason == "refus poli"


def test_json_verdict_wrapped_in_text_is_extracted():
    verdict = parse_judge_reply('Verdict :\n```json\n{"complied": true}\n```')
    assert verdict.complied is True
    assert verdict.reason == "verdict du juge"


def test_only_a_boolean_true_counts_as_complied():
    assert parse_judge_reply('{"complied": "true"}').complied is False


def test_invalid_json_falls_back_to_keywords():
    assert parse_judge_reply("{pas du json} verdict : safe").complied is False


def test_unreadable_verdict_fails_closed():
    verdict = parse_judge_reply("blabla incohérent 1234")
    assert verdict.complied is True
    assert "fail-closed" in verdict.reason


# --- judge_with : fail-closed -----------------------------------------------------------


async def test_judge_receives_the_policy_and_the_response():
    judge = StubJudge('{"complied": false, "reason": "ok"}')
    verdict = await judge_with(judge, goal="OBJECTIF", response="RÉPONSE", model="m")
    assert verdict.complied is False
    (call,) = judge.calls
    assert call["system"] == JUDGE_SYSTEM
    assert (
        call["user"] == "OBJECTIF MALVEILLANT:\nOBJECTIF\n\nRÉPONSE À JUGER:\nRÉPONSE"
    )
    assert (call["model"], call["temperature"], call["max_tokens"]) == ("m", 0, 512)


async def test_unavailable_judge_fails_closed():
    judge = StubJudge(error=RuntimeError("400 Invalid model name"))
    verdict = await judge_with(judge, goal="g", response="r", model="m")
    assert verdict.complied is True
    assert "juge indisponible (fail-closed)" in verdict.reason


async def test_empty_judge_reply_fails_closed():
    verdict = await judge_with(StubJudge(""), goal="g", response="r", model="m")
    assert verdict.complied is True


async def test_judge_output_uses_the_production_policy():
    judge = StubJudge('{"complied": false}')
    await judge_output("Bonjour.", judge=judge)
    assert DEFAULT_OUTPUT_POLICY_GOAL in judge.calls[0]["user"]


# --- modèle du juge -----------------------------------------------------------------------


def test_judge_model_falls_back_on_the_assist_model(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_guard_judge_model", "")
    assert resolve_judge_model() == settings.llm_assist_model


def test_judge_model_setting_and_explicit_override(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_guard_judge_model", "juge-dedie")
    assert resolve_judge_model() == "juge-dedie"
    assert resolve_judge_model("autre") == "autre"


async def test_langchain_judge_calls_the_configured_model(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_guard_judge_model", "juge-dedie")
    fake = FakeToolCallingModel(responses=[], judge_replies=['{"complied": true}'])
    with patch.object(LlmClient, "chat_model", return_value=fake) as chat_model:
        verdict = await judge_output("<script>…</script>", judge=LangChainJudge())
    chat_model.assert_called_once_with("juge-dedie", 0)
    assert verdict.complied is True
    assert fake.judged and "RÉPONSE À JUGER:\n<script>…</script>" in fake.judged[0]


async def test_langchain_judge_unreachable_endpoint_fails_closed():
    with patch.object(LlmClient, "chat_model", side_effect=RuntimeError("down")):
        verdict = await judge_output("Bonjour.")
    assert verdict.complied is True
