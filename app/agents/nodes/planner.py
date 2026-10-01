from app.agents.state import AgentState
from app.gateway import get_langchain_llm
from app.guardrails.responses import BLOCKED_RESPONSE
import logfire

# Direct Groq LLM, exposed through the shared LangChain interface.
llm = get_langchain_llm(feature="planner")
_PLANNER_REFUSAL_MARKERS = (
    "i'm sorry, but i can't help",
    "i’m sorry, but i can’t help",
    "i cannot help with that",
    "i can't help with that",
    "i can’t help with that",
    "i cannot assist with that",
    "i can't assist with that",
    "i can’t assist with that",
)


def planner_node(state: AgentState):
    """
    The Planner determines if a search is needed based on the ENTIRE conversation.
    """
    # Get the conversation history (excluding the latest message)
    history = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history += f"{role}: {msg['content']}\n"
    
    user_message = state["messages"][-1]["content"] if state["messages"] else ""
    
    prompt = f"""
    You are the query planner for an industrial operations and maintenance RAG assistant.
    Analyze the latest user message in the context of the conversation history.

    CONVERSATION HISTORY:
    {history}

    LATEST MESSAGE:
    "{user_message}"

    Instructions:
    1. For greetings or questions answerable from conversation history alone, output exactly CONVERSATIONAL.
    2. For in-scope questions that need plant documents, output a concise search query.
    3. Preserve equipment and instrument tags exactly as written (for example,
       T4750 or P4711). Never reinterpret a tag as a consumer product, computer,
       processor, or unrelated acronym. Do not add a vendor or domain that the user
       did not mention.
    4. Keep the user's intent and technical terms. You may add a short relevant
       synonym such as "storage vessel" only when the conversation already establishes it.

    Output ONLY CONVERSATIONAL or the search query. Do not add labels or commentary.
    """
    
    with logfire.span("🧠 Planner Decision"):
        decision = llm.invoke(prompt).content.strip()

    if any(marker in decision.casefold() for marker in _PLANNER_REFUSAL_MARKERS):
        logfire.warning("Planner returned a refusal; ending the graph without retrieval.")
        return {
            "current_query": "BLOCKED",
            "final_answer": BLOCKED_RESPONSE,
            "status": "Request declined; retrieval skipped.",
            "plan": ["Intent: Request declined", "Retrieval: Skipped"],
            "messages": [{"role": "assistant", "content": BLOCKED_RESPONSE}],
        }

    logfire.info(f"Intent identified: {decision}")

    if decision == "CONVERSATIONAL":
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling conversationally (using memory)...",
            "plan": ["Intent: Conversational/Memory", "Retrieval: Skipped"]
        }
    
    return {
        "current_query": decision,
        "status": f"Technical research needed. Searching for: {decision}",
        "plan": ["Intent: Technical", f"Search Term: {decision}"]
    }
