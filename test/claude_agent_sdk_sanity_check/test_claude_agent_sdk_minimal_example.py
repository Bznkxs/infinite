# claude agent sdk minimal example

import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions


async def test_claude_agent_sdk_minimal_example():
    result = None
    async for message in query(
        prompt="What files are in this directory?",
        options=ClaudeAgentOptions(allowed_tools=["Bash", "Glob"]),
    ):
        if hasattr(message, "result"):
            print(message.result)
            result = message.result
    assert result is not None



if __name__ == "__main__":  # redundant for pytest, but kept for manual testing
    asyncio.run(test_claude_agent_sdk_minimal_example())