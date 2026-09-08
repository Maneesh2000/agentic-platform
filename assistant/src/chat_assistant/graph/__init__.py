"""The agent's brain as a LangGraph.

Built now: a single `chat` node behind a real conditional edge, compiled
and streamed through `livekit.plugins.langchain.LLMAdapter`. Deliberately
identical in behavior to the plain LLM it replaces.

Later (deferred by decision): web search, document extraction, and tool
orchestration land as nodes/subgraphs behind `router.route` — see
`specialists/registry.py`. Adding one must never require restructuring.

NOTE (gotcha 4): LLMAdapter accepts compiled LangGraphs, `create_agent`,
and deep agents — NOT plain LCEL chains (`prompt | llm | parser`).
"""
