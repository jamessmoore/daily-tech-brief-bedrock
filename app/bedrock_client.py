"""Thin wrapper around the Bedrock Converse API with a tool-use loop."""

from __future__ import annotations

import logging
from typing import Any, Callable

import boto3

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6

ToolHandler = Callable[[dict[str, Any]], Any]


class BedrockConverseClient:
    def __init__(self, model_id: str, region_name: str | None = None) -> None:
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def converse_text(self, system_prompt: str, user_message: str) -> str:
        """Single Converse call with no tools — used by the synthesizer step."""
        messages = [{"role": "user", "content": [{"text": user_message}]}]
        response = self._converse(system_prompt, messages, tool_config=None)
        return self._extract_text(response["output"]["message"])

    def run_tool_loop(
        self,
        system_prompt: str,
        user_message: str,
        tool_specs: list[dict[str, Any]],
        tool_handlers: dict[str, ToolHandler],
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> str:
        """Send a message, dispatch any tool_use blocks the model returns, and
        resend tool_result blocks until the model answers with text only (or
        the iteration cap is hit, at which point we force a final answer)."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": user_message}]}
        ]
        tool_config = {"tools": tool_specs} if tool_specs else None

        output_message: dict[str, Any] | None = None
        for iteration in range(1, max_iterations + 1):
            logger.info("Bedrock tool loop iteration %d/%d", iteration, max_iterations)
            response = self._converse(system_prompt, messages, tool_config)
            output_message = response["output"]["message"]
            messages.append(output_message)

            tool_uses = [
                block["toolUse"] for block in output_message["content"] if "toolUse" in block
            ]
            if not tool_uses:
                return self._extract_text(output_message)

            messages.append(
                {
                    "role": "user",
                    "content": [self._dispatch_tool(tu, tool_handlers) for tu in tool_uses],
                }
            )

        logger.warning(
            "Hit max tool iterations (%d) without a final answer; forcing a text-only response",
            max_iterations,
        )
        response = self._converse(system_prompt, messages, tool_config=None)
        return self._extract_text(response["output"]["message"])

    def _converse(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": self._model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
        }
        if tool_config:
            kwargs["toolConfig"] = tool_config
        return self._client.converse(**kwargs)

    def _dispatch_tool(
        self, tool_use: dict[str, Any], tool_handlers: dict[str, ToolHandler]
    ) -> dict[str, Any]:
        name = tool_use["name"]
        tool_use_id = tool_use["toolUseId"]
        handler = tool_handlers.get(name)
        if handler is None:
            logger.error("No handler registered for tool %r", name)
            return {
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [{"text": f"ERROR: no handler for tool {name}"}],
                    "status": "error",
                }
            }
        try:
            result = handler(tool_use.get("input", {}))
            content = (
                [{"json": result}] if isinstance(result, (dict, list)) else [{"text": str(result)}]
            )
            return {"toolResult": {"toolUseId": tool_use_id, "content": content}}
        except Exception as exc:  # noqa: BLE001 - surface any tool failure to the model
            logger.exception("Tool %r raised an exception", name)
            return {
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [{"text": f"ERROR: {exc}"}],
                    "status": "error",
                }
            }

    @staticmethod
    def _extract_text(message: dict[str, Any]) -> str:
        return "".join(block["text"] for block in message["content"] if "text" in block)
