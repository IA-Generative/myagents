"""Garde anti-prompt-injection (OWASP LLM01), portage de `@mirai/prompt-guard`.

- `core`   : heuristiques pures, durcissement du system prompt, messages, log ;
- `judge`  : LLM-juge fail-closed, branché sur le client LLM de l'application ;
- `config` : posture par défaut (anomalie en audit, fail-closed).

L'orchestration par route (journal en base, erreurs 422) vit dans
`app.services.prompt_guard`.
"""

from app.llm.guard.config import DEFAULT_GUARD_CONFIG, GuardConfig
from app.llm.guard.core import (
    BLOCK_MESSAGE_AGENT_CONFIG,
    BLOCK_MESSAGE_OUTPUT,
    BLOCK_MESSAGE_USER_INPUT,
    DEFAULT_ANOMALY,
    INJECTION_MARKERS,
    KEYLOGGER_SIGNATURES,
    AnomalyConfig,
    GuardResult,
    Signal,
    StreamingOutputInspector,
    Verdict,
    anomaly_detector,
    anomaly_score,
    deobfuscate,
    harden_system_prompt,
    inspect_input,
    inspect_output,
    keylogger_detector,
    log_guard_event,
    make_canary,
    prompt_leak_detector,
)
from app.llm.guard.judge import (
    DEFAULT_OUTPUT_POLICY_GOAL,
    JUDGE_SYSTEM,
    LangChainJudge,
    LlmJudge,
    judge_output,
    judge_with,
    parse_judge_reply,
    parse_keyword_verdict,
    resolve_judge_model,
)

__all__ = [
    "BLOCK_MESSAGE_AGENT_CONFIG",
    "BLOCK_MESSAGE_OUTPUT",
    "BLOCK_MESSAGE_USER_INPUT",
    "DEFAULT_ANOMALY",
    "DEFAULT_GUARD_CONFIG",
    "DEFAULT_OUTPUT_POLICY_GOAL",
    "INJECTION_MARKERS",
    "JUDGE_SYSTEM",
    "KEYLOGGER_SIGNATURES",
    "AnomalyConfig",
    "GuardConfig",
    "GuardResult",
    "LangChainJudge",
    "LlmJudge",
    "Signal",
    "StreamingOutputInspector",
    "Verdict",
    "anomaly_detector",
    "anomaly_score",
    "deobfuscate",
    "harden_system_prompt",
    "inspect_input",
    "inspect_output",
    "judge_output",
    "judge_with",
    "keylogger_detector",
    "log_guard_event",
    "make_canary",
    "parse_judge_reply",
    "parse_keyword_verdict",
    "prompt_leak_detector",
    "resolve_judge_model",
]
