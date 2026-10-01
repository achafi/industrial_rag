import logfire
from app.agents.state import AgentState
from app.gateway import get_langchain_llm


def generate_node(state: AgentState):
    """
    Synthesizes a response using both Documentation Context AND Conversation History.
    Uses the configured Groq model through LangChain.
    """
    query = state["current_query"]

    history_str = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")
        prompt = f"""
        You are a friendly and helpful Enterprise AI Assistant.
        Answer the user's latest message using the CONVERSATION HISTORY below.

        CONVERSATION HISTORY:
        {history_str}

        LATEST MESSAGE:
        "{user_msg}"
        """
    else:
        logfire.info("Generating technical RAG response.")
        max_context_chars = 25000
        full_context = ""

        for doc in state["documents"]:
            if len(full_context) + len(doc) < max_context_chars:
                full_context += doc + "\n\n"
            else:
                logfire.warning("Context truncated to fit Groq TPM limits.")
                break

        prompt = f"""
        You are an industrial operations and maintenance information assistant.
        Answer the user's question using the supplied plant-document context.
        Keep equipment and instrument tags exactly as written. Do not infer missing
        specifications, P&ID connections, or operating limits. If the context does
        not support an answer, state what is missing and name the controlled record
        or site role that should be consulted. Do not present this response as work
        authorization; remind the user to follow approved site procedures where
        intervention or abnormal conditions are involved.

        PLANT DOCUMENT CONTEXT:
        {full_context}

        CONVERSATION HISTORY:
        {history_str}

        USER QUESTION:
        "{user_msg}"
        """

    with logfire.span("✍️ LLM Synthesis"):
        try:
            response = get_langchain_llm(feature="responder").invoke(prompt)
            content = response.content
            logfire.info("✅ Response synthesised via Groq.")
            plan_update = state["plan"]
            status = "Response generated."

            return {
                "final_answer": content,
                "status": status,
                "plan": plan_update,
                "messages": [{"role": "assistant", "content": content}]
            }

        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            raise e
