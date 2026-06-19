from unittest.mock import MagicMock

from tools.web_search import (
    MAX_CONTENT_CHARS,
    MAX_RESULTS_PER_SEARCH,
    WEB_SEARCH_TOOL_SPEC,
    web_search,
    web_search_tool_handler,
)


def test_web_search_tool_spec_shape():
    spec = WEB_SEARCH_TOOL_SPEC["toolSpec"]
    assert spec["name"] == "web_search"
    assert spec["inputSchema"]["json"]["required"] == ["query"]
    assert spec["inputSchema"]["json"]["properties"]["query"]["type"] == "string"


def test_web_search_sends_query_and_api_key_and_parses_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"title": "T1", "url": "https://a", "content": "C1"},
            {"title": "T2", "url": "https://b", "content": "C2"},
        ]
    }
    mock_response.raise_for_status.return_value = None

    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return mock_response

    monkeypatch.setattr("tools.web_search.requests.post", fake_post)

    results = web_search("aws lambda news")

    assert captured["json"]["query"] == "aws lambda news"
    assert captured["json"]["api_key"] == "fake-key"
    assert captured["json"]["max_results"] == MAX_RESULTS_PER_SEARCH
    assert results == [
        {"title": "T1", "url": "https://a", "content": "C1"},
        {"title": "T2", "url": "https://b", "content": "C2"},
    ]


def test_web_search_truncates_long_content(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

    long_content = "x" * (MAX_CONTENT_CHARS + 100)
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [{"title": "T1", "url": "https://a", "content": long_content}]
    }
    mock_response.raise_for_status.return_value = None
    monkeypatch.setattr("tools.web_search.requests.post", lambda *a, **k: mock_response)

    results = web_search("aws lambda news")

    assert len(results[0]["content"]) == MAX_CONTENT_CHARS + len("...")
    assert results[0]["content"].endswith("...")


def test_web_search_tool_handler_adapts_dict_input(monkeypatch):
    monkeypatch.setattr("tools.web_search.web_search", lambda query: [{"query": query}])
    assert web_search_tool_handler({"query": "x"}) == [{"query": "x"}]
