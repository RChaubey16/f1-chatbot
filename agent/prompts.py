"""Prompt templates for the F1 RAG agent."""

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

ROUTER_SYSTEM = (
    "You are a query classifier. Respond with exactly one word: "
    "HISTORICAL, CURRENT, or MIXED. No punctuation, no explanation."
)

ROUTER_PROMPT = """\
Classify this Formula One query. The current year is 2026. The current F1 season is 2026.

Query: {query}

Rules:
- HISTORICAL: about any season before 2026, race history, past champions, driver/team biographies
- CURRENT: about the 2026 season specifically, live standings, upcoming races
- MIXED: requires both historical context and 2026 season data

One word only:"""


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = (
    "You are a Formula One expert assistant. "
    "Answer using ONLY the information in the provided context. "
    "Do not use any knowledge from your training data. "
    "If the context does not contain enough information to answer, say so. "
    "Be concise and cite sources when possible."
)

ANSWER_PROMPT = """\
Question: {question}

Context:
{context}

Answer the question using only the context above:"""
