import json
import sys
from pathlib import Path

import pytest
from mcp_client import McpClientError, StdioMcpClient

FAKE_SERVER = Path(__file__).parent / "fake_mcp_server.py"


def _client() -> StdioMcpClient:
    return StdioMcpClient([sys.executable, str(FAKE_SERVER)])


def test_initialize_and_call_tool_round_trip():
    with _client() as client:
        result = client.call_tool("echo", {"message": "hello"})

    payload = json.loads(result["content"][0]["text"])
    assert payload == {"tool": "echo", "arguments": {"message": "hello"}}


def test_call_tool_raises_mcp_client_error_on_isError_result():
    with _client() as client:
        with pytest.raises(McpClientError, match="boom"):
            client.call_tool("fail", {})


def test_multiple_calls_on_one_connection_use_distinct_request_ids():
    with _client() as client:
        first = client.call_tool("echo", {"n": 1})
        second = client.call_tool("echo", {"n": 2})

    assert json.loads(first["content"][0]["text"])["arguments"] == {"n": 1}
    assert json.loads(second["content"][0]["text"])["arguments"] == {"n": 2}


def test_close_is_safe_to_call_twice():
    client = _client()
    client.start()
    client.close()
    client.close()  # should not raise
