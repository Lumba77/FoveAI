"""
Unit tests for Forge Nursery Micro Tools Engine and Custom Tool registration.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Forge.nursery.micro_tools import get_micro_tool_engine, MicroTool


def test_micro_tools_lifecycle():
    engine = get_micro_tool_engine()
    tools = engine.list_tools()
    assert len(tools) >= 4, f"Expected at least 4 built-in tools, got {len(tools)}"
    
    # Check built-in tool presence
    tool_ids = [t["id"] for t in tools]
    assert "ui_action_router" in tool_ids
    assert "code_quickfix" in tool_ids
    assert "data_crystallizer" in tool_ids
    assert "sentry_diagnostics" in tool_ids

    # Test registering a custom tool
    custom = engine.register_tool(
        tool_id="test_custom_greeter",
        name="Test Greeter Tool",
        description="Greets the user in JSON format",
        system_prompt="Return a JSON object: {\"greeting\": \"hello\"}",
        output_type="json",
    )
    assert custom.id == "test_custom_greeter"
    assert engine.get_tool("test_custom_greeter") is not None
    print("✓ Micro Tools lifecycle and custom tool registration OK")


if __name__ == "__main__":
    test_micro_tools_lifecycle()
