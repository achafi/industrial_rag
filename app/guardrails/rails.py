import logfire
import re
from langchain_groq import ChatGroq
from nemoguardrails import RailsConfig, LLMRails
from nemoguardrails.rails.llm.options import RailStatus

from app.config import settings
from app.guardrails.colang_rules import COLANG_CONTENT, YAML_CONTENT
from app.guardrails.responses import BLOCKED_RESPONSE


_rails: LLMRails | None = None

_EXPLICIT_BYPASS_PATTERNS = (
    re.compile(r"\bignore\b.{0,80}\b(?:rules|instructions|guidelines|guardrails)\b", re.IGNORECASE),
    re.compile(r"\b(?:bypass|circumvent|evade)\b.{0,100}\b(?:site[’']?s?\s+)?(?:safety\s+)?(?:procedures|rules|controls|guardrails)\b", re.IGNORECASE),
    re.compile(r"\b(?:defeat|disable|bypass|circumvent)\b.{0,80}\b(?:equipment\s+)?(?:safety\s+)?(?:interlock|trip|guard)\b", re.IGNORECASE),
)


def initialize_rails() -> None:
    """
    Build the NeMo LLMRails singleton at app startup.
    Uses the configured Groq model for intent classification at the gate.
    """
    global _rails

    guard_llm = ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0
    )

    config = RailsConfig.from_content(
        colang_content=COLANG_CONTENT,
        yaml_content=YAML_CONTENT.replace("__GROQ_MODEL__", settings.GROQ_MODEL)
    )

    _rails = LLMRails(config, llm=guard_llm)
    logfire.info(f"🛡️ NeMo Guardrails initialised ({settings.GROQ_MODEL}).")
    
    


def guard(message: str) -> tuple[bool, str | None]:
    """
    Run a user message through the NeMo rails gate.

    Returns:
        (True,  rail_response) — a rail fired; return this response immediately,
                                skip the RAG pipeline entirely.
        (False, None)          — message is clean; proceed to LangGraph.
    """
    if any(pattern.search(message) for pattern in _EXPLICIT_BYPASS_PATTERNS):
        logfire.warning("🛡️ Explicit safety bypass request blocked before NeMo and RAG.")
        return True, BLOCKED_RESPONSE

    if _rails is None:
        logfire.warning("⚠️ Guardrails not initialised — skipping gate.")
        return False, None

    with logfire.span("🛡️ Guardrails Check"):
        # Check only the configured NeMo input rails; do not generate and then
        # discard an unrelated assistant response before starting the RAG flow.
        result = _rails.check(messages=[{"role": "user", "content": message}])

        if result.status == RailStatus.BLOCKED:
            logfire.info(f"🛡️ Guardrails blocked input | rail={result.rail}")
            return True, result.content

        logfire.info("✅ NeMo input rails passed.")
        return False, None
