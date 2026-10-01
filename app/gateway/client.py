"""Direct Groq LLM client shared by the planner and response generator."""
from langchain_groq import ChatGroq

from app.config import settings


def get_langchain_llm(feature: str = "rag") -> ChatGroq:
    """Create a Groq chat model; ``feature`` is retained for call-site clarity."""
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL,
        temperature=0,
    )
