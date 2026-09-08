"""Graph state threaded through every node."""

# import operator  # uncomment with the fan-out fields below
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Conversation state.

    `add_messages` merges each node's returned messages into the running
    list (append + de-dupe by id) instead of overwriting it.
    """

    messages: Annotated[list[BaseMessage], add_messages]

    # Who is asking, for the audit trail only — never for authorization.
    # Text passes the signed-in user through; voice has no identity today
    # (the LiveKit token sets no participant metadata), so it degrades to
    # "anon" honestly rather than fabricating one.
    actor: str

    # --- fan-out seam (unused today) -------------------------------------
    # When specialists land, the router emits one Send("<name>", {...}) per
    # task; each specialist appends to `findings` (operator.add lets N
    # parallel branches merge without clobbering) and an aggregate node
    # folds them into one spoken reply.
    #
    # tasks: list[str]
    # findings: Annotated[list[dict], operator.add]
