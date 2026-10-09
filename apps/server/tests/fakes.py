"""Test doubles shared across LLM-related unit/integration tests."""

import json
import re

import httpx
import openai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.llm.guard import JUDGE_SYSTEM

# Signature de CODE keylogger (pas le mot « keylogger », présent dans la politique du juge).
_HOSTILE_CODE_RE = re.compile(
    r"localStorage\s*\.\s*keys|String\.fromCharCode", re.IGNORECASE
)


def is_judge_call(messages: list[BaseMessage]) -> bool:
    return any(
        isinstance(m, SystemMessage) and m.content == JUDGE_SYSTEM for m in messages
    )


def default_judge_reply(messages: list[BaseMessage]) -> str:
    """Verdict JSON du juge simulé : cédé si la réponse jugée porte du code keylogger."""
    judged = str(messages[-1].content).split("RÉPONSE À JUGER:", 1)[-1]
    complied = bool(_HOSTILE_CODE_RE.search(judged))
    return json.dumps({"complied": complied, "reason": "juge simulé"})


class FakeToolCallingModel(BaseChatModel):
    """Minimal chat model stand-in: replays a fixed queue of AIMessage responses.

    `create_agent` calls `.bind_tools(...)` before every model turn, so a fake
    used in its place must implement that method (a no-op here is enough).

    Les appels du LLM-juge de la garde (reconnus à leur message système) ne
    consomment pas la file : ils reçoivent `judge_replies` dans l'ordre, sinon un
    verdict simulé (cédé si la réponse jugée contient du code keylogger).
    """

    responses: list[BaseMessage]
    seen_messages: list[BaseMessage] = Field(default_factory=list)
    judge_replies: list[str] = Field(default_factory=list)
    judged: list[str] = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if is_judge_call(messages):
            self.judged.append(str(messages[-1].content))
            raw = (
                self.judge_replies.pop(0)
                if self.judge_replies
                else default_judge_reply(messages)
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(raw))])
        message = self.responses.pop(0)
        self.seen_messages = list(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"


_HUB_REQUEST = httpx.Request("POST", "http://hub/v1/chat/completions")


class RetiredModel(FakeToolCallingModel):
    """Le hub refuse ce nom de modèle : retiré ou renommé par l'opérateur."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if is_judge_call(messages):
            return super()._generate(messages, stop, run_manager, **kwargs)
        raise openai.BadRequestError(
            'no service for path "/v1/chat/completions" with model "gpt-oss-120b"',
            response=httpx.Response(400, request=_HUB_REQUEST),
            body=None,
        )


class HubDown(FakeToolCallingModel):
    """Le hub ne répond pas (connexion refusée, délai dépassé)."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if is_judge_call(messages):
            return super()._generate(messages, stop, run_manager, **kwargs)
        raise openai.APIConnectionError(request=_HUB_REQUEST)
