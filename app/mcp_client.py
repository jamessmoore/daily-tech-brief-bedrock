"""Minimal stdio MCP client: spawn the slack-poster server as a Node
subprocess, perform the MCP `initialize` handshake over JSON-RPC 2.0
(newline-delimited framing, per the MCP stdio transport spec), and call its
`post_to_slack` tool with the finished brief.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SLACK_MCP_SERVER_DIR = Path(__file__).parent / "slack_mcp_server"
SLACK_MCP_SERVER_ENTRYPOINT = SLACK_MCP_SERVER_DIR / "index.js"

READ_TIMEOUT_SECONDS = 15


class McpClientError(RuntimeError):
    pass


class StdioMcpClient:
    """A short-lived MCP client: one subprocess, one initialize handshake,
    one or more tool calls, then terminate. Not reused across invocations."""

    def __init__(self, command: list[str], cwd: Path | None = None) -> None:
        self._command = command
        self._cwd = cwd
        self._process: subprocess.Popen[str] | None = None
        self._next_id = 1

    def __enter__(self) -> "StdioMcpClient":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def start(self) -> None:
        logger.info("Starting MCP server subprocess: %s", self._command)
        self._process = subprocess.Popen(
            self._command,
            cwd=self._cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._initialize()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        result = response.get("result", {})
        if result.get("isError"):
            text = _result_text(result)
            raise McpClientError(f"MCP tool {name!r} returned an error: {text}")
        return result

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "daily-tech-brief-bedrock", "version": "1.0.0"},
            },
        )
        self._notify("notifications/initialized", {})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._process is None:
            raise McpClientError("MCP client is not started")

        request_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self._write(message)

        response = self._read()
        if response.get("id") != request_id:
            raise McpClientError(
                f"Expected response id {request_id}, got {response.get('id')!r}: {response}"
            )
        if "error" in response:
            raise McpClientError(f"MCP error on {method!r}: {response['error']}")
        return response

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        if self._process is None:
            raise McpClientError("MCP client is not started")
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, message: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        line = json.dumps(message) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        assert self._process is not None and self._process.stdout is not None
        line = self._process.stdout.readline()
        if not line:
            stderr_output = ""
            if self._process.stderr is not None:
                stderr_output = self._process.stderr.read()
            raise McpClientError(
                f"MCP server closed stdout unexpectedly. stderr: {stderr_output}"
            )
        return json.loads(line)


def _result_text(result: dict[str, Any]) -> str:
    content = result.get("content", [])
    return " ".join(block.get("text", "") for block in content if "text" in block)


def post_brief_to_slack(brief_text: str, channel: str = "#daily-brief") -> dict[str, Any]:
    """Spawn the vendored slack-poster MCP server and post the brief via its
    `post_to_slack` tool. Returns the MCP tool result."""
    with StdioMcpClient(["node", str(SLACK_MCP_SERVER_ENTRYPOINT)]) as client:
        return client.call_tool("post_to_slack", {"message": brief_text, "channel": channel})
