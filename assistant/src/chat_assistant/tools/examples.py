"""Example tool showing the @function_tool shape: typed args + docstring
become the LLM-facing schema; raise ToolError for a user-speakable failure.
"""

import logging

from livekit.agents import RunContext, function_tool

logger = logging.getLogger("chat-assistant.tools")


@function_tool
async def lookup_weather(context: RunContext, location: str) -> str:
    """Look up current weather for a location.

    If the location is unsupported, tell the user its weather is unavailable.

    Args:
        location: City or place name, e.g. "Hyderabad".
    """
    logger.info("weather lookup for %s", location)
    # Placeholder result — swap for a real weather API when needed.
    return "It is sunny with a temperature of twenty five degrees Celsius."
