"""Lambda entrypoint: load secrets, run the researcher -> synthesizer pipeline,
then deliver the finished brief to Slack via the vendored MCP server."""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from bedrock_client import BedrockConverseClient
from mcp_client import McpClientError, post_brief_to_slack
from tools.web_search import WEB_SEARCH_TOOL_SPEC, web_search_tool_handler

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#daily-brief")
TAVILY_SECRET_ARN = os.environ.get("TAVILY_SECRET_ARN")
SLACK_SECRET_ARN = os.environ.get("SLACK_SECRET_ARN")

_secrets_loaded = False


def _load_secrets() -> None:
    """Pull Tavily/Slack credentials from Secrets Manager into the process
    environment once per cold start. Subsequent warm invocations skip the
    Secrets Manager round trip entirely."""
    global _secrets_loaded
    if _secrets_loaded:
        return

    client = boto3.client("secretsmanager", region_name=AWS_REGION)

    if TAVILY_SECRET_ARN and "TAVILY_API_KEY" not in os.environ:
        os.environ["TAVILY_API_KEY"] = _get_secret_value(client, TAVILY_SECRET_ARN)

    if SLACK_SECRET_ARN and "SLACK_BOT_TOKEN" not in os.environ:
        os.environ["SLACK_BOT_TOKEN"] = _get_secret_value(client, SLACK_SECRET_ARN)

    _secrets_loaded = True


def _get_secret_value(client: Any, secret_id: str) -> str:
    return client.get_secret_value(SecretId=secret_id)["SecretString"]


def _read_prompt(filename: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    _load_secrets()

    bedrock = BedrockConverseClient(model_id=BEDROCK_MODEL_ID, region_name=AWS_REGION)

    logger.info("Starting researcher step")
    try:
        research_notes = bedrock.run_tool_loop(
            system_prompt=_read_prompt("researcher_system.md"),
            user_message=(
                "Research the last 24-48 hours of DevOps, AI/ML, MCP, and cloud "
                "infrastructure news. Use the web_search tool as needed."
            ),
            tool_specs=[WEB_SEARCH_TOOL_SPEC],
            tool_handlers={"web_search": web_search_tool_handler},
        )
    except Exception:
        logger.exception("Researcher step failed")
        raise
    logger.info("Researcher step complete (%d chars of notes)", len(research_notes))

    logger.info("Starting synthesizer step")
    try:
        brief = bedrock.converse_text(
            system_prompt=_read_prompt("synthesizer_system.md"),
            user_message=research_notes,
        )
    except Exception:
        logger.exception("Synthesizer step failed")
        raise
    logger.info("Synthesizer step complete (%d chars)", len(brief))

    logger.info("Posting brief to Slack channel %s", SLACK_CHANNEL)
    try:
        slack_result = post_brief_to_slack(brief, channel=SLACK_CHANNEL)
    except McpClientError:
        logger.exception("Slack delivery failed")
        raise
    logger.info("Slack delivery complete")

    return {
        "statusCode": 200,
        "researchChars": len(research_notes),
        "briefChars": len(brief),
        "slackResult": slack_result,
    }
