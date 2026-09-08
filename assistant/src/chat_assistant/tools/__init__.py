"""Function-tool registry. Everything in TOOLS attaches to the Assistant.

Scope caveat, verified against the plugin source: when USE_LANGGRAPH=true,
`LLMAdapter.chat()` receives these tools but tool *execution* happens inside
LangGraph — so LiveKit-side tools only fire on the direct path
(USE_LANGGRAPH=false). When tool orchestration lands, tools move into the
graph (bind_tools + ToolNode) and this registry becomes their catalog.
"""

from .examples import lookup_weather

TOOLS = [lookup_weather]
