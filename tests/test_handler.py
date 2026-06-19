import os
from unittest.mock import MagicMock

import handler
import pytest
from mcp_client import McpClientError


class FakeBedrockClient:
    """Stands in for BedrockConverseClient so tests exercise handler.py's
    orchestration (stage order, error propagation, return shape) without
    making any real Bedrock calls."""

    def __init__(self, research_notes="research notes", brief="final brief",
                 research_exc=None, synth_exc=None):
        self.research_notes = research_notes
        self.brief = brief
        self.research_exc = research_exc
        self.synth_exc = synth_exc
        self.run_tool_loop_calls = []
        self.converse_text_calls = []

    def run_tool_loop(self, **kwargs):
        self.run_tool_loop_calls.append(kwargs)
        if self.research_exc:
            raise self.research_exc
        return self.research_notes

    def converse_text(self, **kwargs):
        self.converse_text_calls.append(kwargs)
        if self.synth_exc:
            raise self.synth_exc
        return self.brief


@pytest.fixture(autouse=True)
def isolate_handler_state(monkeypatch):
    """_load_secrets() caches into a module global and into real os.environ
    keys (TAVILY_API_KEY/SLACK_BOT_TOKEN) directly, bypassing monkeypatch's
    own tracking -- force a clean slate before every test rather than relying
    on monkeypatch to undo it."""
    monkeypatch.setattr(handler, "_secrets_loaded", False)
    monkeypatch.setattr(handler, "TAVILY_SECRET_ARN", None)
    monkeypatch.setattr(handler, "SLACK_SECRET_ARN", None)
    monkeypatch.setattr(handler.boto3, "client", MagicMock())
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ.pop("SLACK_BOT_TOKEN", None)


def test_lambda_handler_happy_path_runs_all_three_stages_in_order(monkeypatch):
    fake_bedrock = FakeBedrockClient(research_notes="raw research", brief="the brief")
    monkeypatch.setattr(handler, "BedrockConverseClient", lambda **kwargs: fake_bedrock)

    slack_calls = []

    def fake_post_brief_to_slack(brief_text, channel):
        slack_calls.append((brief_text, channel))
        return {"content": [{"text": "Posted successfully."}]}

    monkeypatch.setattr(handler, "post_brief_to_slack", fake_post_brief_to_slack)

    result = handler.lambda_handler({}, None)

    assert result == {
        "statusCode": 200,
        "researchChars": len("raw research"),
        "briefChars": len("the brief"),
        "slackResult": {"content": [{"text": "Posted successfully."}]},
    }
    # synthesizer must receive the researcher's output as its input
    assert fake_bedrock.converse_text_calls[0]["user_message"] == "raw research"
    # slack delivery must receive the synthesizer's output, on the configured channel
    assert slack_calls == [("the brief", handler.SLACK_CHANNEL)]


def test_lambda_handler_researcher_failure_skips_synthesizer_and_slack(monkeypatch):
    fake_bedrock = FakeBedrockClient(research_exc=RuntimeError("search down"))
    monkeypatch.setattr(handler, "BedrockConverseClient", lambda **kwargs: fake_bedrock)

    slack_calls = []
    monkeypatch.setattr(
        handler, "post_brief_to_slack", lambda *a, **k: slack_calls.append((a, k))
    )

    with pytest.raises(RuntimeError, match="search down"):
        handler.lambda_handler({}, None)

    assert fake_bedrock.converse_text_calls == []
    assert slack_calls == []


def test_lambda_handler_synthesizer_failure_skips_slack(monkeypatch):
    fake_bedrock = FakeBedrockClient(
        research_notes="raw research", synth_exc=ValueError("model error")
    )
    monkeypatch.setattr(handler, "BedrockConverseClient", lambda **kwargs: fake_bedrock)

    slack_calls = []
    monkeypatch.setattr(
        handler, "post_brief_to_slack", lambda *a, **k: slack_calls.append((a, k))
    )

    with pytest.raises(ValueError, match="model error"):
        handler.lambda_handler({}, None)

    assert slack_calls == []


def test_lambda_handler_propagates_slack_delivery_failure(monkeypatch):
    fake_bedrock = FakeBedrockClient(research_notes="raw research", brief="the brief")
    monkeypatch.setattr(handler, "BedrockConverseClient", lambda **kwargs: fake_bedrock)

    def failing_post(*args, **kwargs):
        raise McpClientError("slack unreachable")

    monkeypatch.setattr(handler, "post_brief_to_slack", failing_post)

    with pytest.raises(McpClientError, match="slack unreachable"):
        handler.lambda_handler({}, None)


def test_load_secrets_populates_env_from_secrets_manager_then_caches(monkeypatch):
    monkeypatch.setattr(handler, "TAVILY_SECRET_ARN", "arn:tavily")
    monkeypatch.setattr(handler, "SLACK_SECRET_ARN", "arn:slack")

    secret_values = {
        "arn:tavily": {"SecretString": "tavily-key"},
        "arn:slack": {"SecretString": "slack-token"},
    }
    fake_secrets_client = MagicMock()
    fake_secrets_client.get_secret_value.side_effect = (
        lambda SecretId: secret_values[SecretId]
    )
    monkeypatch.setattr(handler.boto3, "client", lambda *a, **k: fake_secrets_client)

    handler._load_secrets()

    assert os.environ["TAVILY_API_KEY"] == "tavily-key"
    assert os.environ["SLACK_BOT_TOKEN"] == "slack-token"
    assert fake_secrets_client.get_secret_value.call_count == 2

    # Second call is a no-op: cached, no further Secrets Manager round trips.
    handler._load_secrets()
    assert fake_secrets_client.get_secret_value.call_count == 2


def test_load_secrets_skips_secrets_manager_when_no_arns_configured(monkeypatch):
    fake_secrets_client = MagicMock()
    monkeypatch.setattr(handler.boto3, "client", lambda *a, **k: fake_secrets_client)

    handler._load_secrets()

    fake_secrets_client.get_secret_value.assert_not_called()
    assert "TAVILY_API_KEY" not in os.environ
    assert "SLACK_BOT_TOKEN" not in os.environ
