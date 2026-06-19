from unittest.mock import MagicMock

from bedrock_client import BedrockConverseClient


def make_client(monkeypatch) -> BedrockConverseClient:
    monkeypatch.setattr("bedrock_client.boto3.client", lambda *a, **k: MagicMock())
    return BedrockConverseClient(model_id="fake-model", region_name="us-east-1")


def text_message(text: str) -> dict:
    return {"role": "assistant", "content": [{"text": text}]}


def tool_use_message(name: str, tool_use_id: str, input_: dict) -> dict:
    return {
        "role": "assistant",
        "content": [{"toolUse": {"toolUseId": tool_use_id, "name": name, "input": input_}}],
    }


def test_converse_text_returns_extracted_text(monkeypatch):
    client = make_client(monkeypatch)
    client._client.converse.return_value = {"output": {"message": text_message("hello world")}}

    assert client.converse_text("system", "user msg") == "hello world"


def test_run_tool_loop_dispatches_tool_and_returns_final_text(monkeypatch):
    client = make_client(monkeypatch)
    client._client.converse.side_effect = [
        {"output": {"message": tool_use_message("web_search", "t1", {"query": "x"})}},
        {"output": {"message": text_message("final answer")}},
    ]
    calls = []

    def handler(tool_input):
        calls.append(tool_input)
        return [{"title": "a", "url": "u", "content": "c"}]

    result = client.run_tool_loop(
        system_prompt="sys",
        user_message="go",
        tool_specs=[{"toolSpec": {"name": "web_search"}}],
        tool_handlers={"web_search": handler},
    )

    assert result == "final answer"
    assert calls == [{"query": "x"}]
    assert client._client.converse.call_count == 2

    # Bedrock's toolResult `json` field must be a JSON *object* -- a tool
    # handler returning a list (like web_search) must get wrapped, not
    # passed through as a bare array. (Caught live against real Bedrock as
    # a ValidationException before this assertion existed.)
    second_call_messages = client._client.converse.call_args_list[1].kwargs["messages"]
    tool_result = second_call_messages[-2]["content"][0]["toolResult"]
    assert tool_result["content"][0]["json"] == {
        "results": [{"title": "a", "url": "u", "content": "c"}]
    }


def test_run_tool_loop_forces_final_answer_at_iteration_cap(monkeypatch):
    client = make_client(monkeypatch)
    # The model never stops requesting tools on its own.
    client._client.converse.side_effect = [
        {"output": {"message": tool_use_message("web_search", f"t{i}", {"query": "x"})}}
        for i in range(3)
    ] + [{"output": {"message": text_message("forced final")}}]

    result = client.run_tool_loop(
        system_prompt="sys",
        user_message="go",
        tool_specs=[{"toolSpec": {"name": "web_search"}}],
        tool_handlers={"web_search": lambda _: "ok"},
        max_iterations=3,
    )

    assert result == "forced final"
    assert client._client.converse.call_count == 4  # 3 tool iterations + 1 forced text-only call

    # Bedrock rejects calls with toolUse/toolResult in history but no
    # toolConfig -- the forced final call must still pass it through, even
    # though we don't want another tool call. (Live regression: dropping it
    # raised "The toolConfig field must be defined when using toolUse and
    # toolResult content blocks.")
    final_call_kwargs = client._client.converse.call_args_list[-1].kwargs
    assert "toolConfig" in final_call_kwargs
    assert final_call_kwargs["toolConfig"] == {"tools": [{"toolSpec": {"name": "web_search"}}]}


def test_run_tool_loop_reports_handler_exception_as_tool_error(monkeypatch):
    client = make_client(monkeypatch)
    client._client.converse.side_effect = [
        {"output": {"message": tool_use_message("web_search", "t1", {"query": "x"})}},
        {"output": {"message": text_message("done")}},
    ]

    def boom(_):
        raise ValueError("nope")

    client.run_tool_loop(
        system_prompt="sys",
        user_message="go",
        tool_specs=[{"toolSpec": {"name": "web_search"}}],
        tool_handlers={"web_search": boom},
    )

    # call_args_list holds a live reference to the mutated `messages` list, so
    # by the time we inspect it a 4th (final-answer) message has been
    # appended; [-2] is the tool-result message sent in this second request.
    second_call_messages = client._client.converse.call_args_list[1].kwargs["messages"]
    tool_result = second_call_messages[-2]["content"][0]["toolResult"]
    assert tool_result["status"] == "error"
    assert "nope" in tool_result["content"][0]["text"]


def test_run_tool_loop_reports_missing_handler_as_tool_error(monkeypatch):
    client = make_client(monkeypatch)
    client._client.converse.side_effect = [
        {"output": {"message": tool_use_message("unknown_tool", "t1", {})}},
        {"output": {"message": text_message("done")}},
    ]

    client.run_tool_loop(
        system_prompt="sys", user_message="go", tool_specs=[], tool_handlers={}
    )

    second_call_messages = client._client.converse.call_args_list[1].kwargs["messages"]
    tool_result = second_call_messages[-2]["content"][0]["toolResult"]
    assert tool_result["status"] == "error"
    assert "unknown_tool" in tool_result["content"][0]["text"]
