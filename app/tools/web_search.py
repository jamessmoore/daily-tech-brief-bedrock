"""Tavily-backed web_search tool: implementation + Bedrock tool spec."""

from __future__ import annotations

import os
from typing import Any

import requests

TAVILY_API_URL = "https://api.tavily.com/search"

# Tavily's `content` field can run several KB per result. The full message
# history (including every prior tool_result) gets resent on every Converse
# call, so by iteration 4+ that compounds into a request body large enough
# to make Bedrock calls stall for 60s+ per attempt in practice. Trimming
# here, at the source, keeps every subsequent turn's payload bounded.
MAX_RESULTS_PER_SEARCH = 5
MAX_CONTENT_CHARS = 400

WEB_SEARCH_TOOL_SPEC: dict[str, Any] = {
    "toolSpec": {
        "name": "web_search",
        "description": (
            "Search the web for recent news and articles. Use this to find "
            "DevOps, AI/ML, MCP, and cloud infrastructure news from the last "
            "24-48 hours. Returns a list of results with title, url, and a "
            "short content snippet."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, e.g. 'AWS Lambda new feature June 2026'",
                    }
                },
                "required": ["query"],
            }
        },
    }
}


def web_search(query: str) -> list[dict[str, str]]:
    """Call the Tavily search API and return a list of {title, url, content} results."""
    api_key = os.environ["TAVILY_API_KEY"]
    response = requests.post(
        TAVILY_API_URL,
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": MAX_RESULTS_PER_SEARCH,
            "days": 2,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "content": _truncate(result.get("content", "")),
        }
        for result in data.get("results", [])
    ]


def _truncate(text: str, limit: int = MAX_CONTENT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def web_search_tool_handler(tool_input: dict[str, Any]) -> list[dict[str, str]]:
    """Adapter matching the BedrockConverseClient tool handler signature."""
    return web_search(tool_input["query"])
