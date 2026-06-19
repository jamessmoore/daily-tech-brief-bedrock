"""Tavily-backed web_search tool: implementation + Bedrock tool spec."""

from __future__ import annotations

import os
from typing import Any

import requests

TAVILY_API_URL = "https://api.tavily.com/search"

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
            "max_results": 8,
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
            "content": result.get("content", ""),
        }
        for result in data.get("results", [])
    ]


def web_search_tool_handler(tool_input: dict[str, Any]) -> list[dict[str, str]]:
    """Adapter matching the BedrockConverseClient tool handler signature."""
    return web_search(tool_input["query"])
