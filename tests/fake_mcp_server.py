#!/usr/bin/env python3
"""Fake MCP stdio server used by test_mcp_client.py.

Implements just enough of the JSON-RPC/MCP stdio protocol (initialize,
notifications/initialized, tools/call) to exercise StdioMcpClient's real
subprocess framing logic without depending on Node or the real
slack-poster server.
"""

import json
import sys


def write(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message = json.loads(line)
        method = message.get("method")
        message_id = message.get("id")

        if method == "initialize":
            write(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {"name": "fake-mcp-server", "version": "0.0.1"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue  # notification, no response expected
        elif method == "tools/call":
            params = message.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name == "fail":
                write(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "result": {"isError": True, "content": [{"text": "boom"}]},
                    }
                )
            else:
                write(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "result": {
                            "content": [
                                {"text": json.dumps({"tool": name, "arguments": arguments})}
                            ]
                        },
                    }
                )
        else:
            write(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()
