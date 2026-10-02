"""Test doubles shared across LLM-related unit/integration tests."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class FakeToolCallingModel(BaseChatModel):
    """Minimal chat model stand-in: replays a fixed queue of AIMessage responses.

    `create_agent` calls `.bind_tools(...)` before every model turn, so a fake
    used in its place must implement that method (a no-op here is enough).
    """

    responses: list[BaseMessage]
    seen_messages: list[BaseMessage] = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self.responses.pop(0)
        self.seen_messages = list(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"
