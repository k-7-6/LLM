import asyncio

import pytest

from anythingllm_mcp.client import AnythingLLMError
from anythingllm_mcp.config import Config, ConfigError
from anythingllm_mcp.server import (
    create_server,
    make_ask_workspace,
    make_create_workspace,
    make_list_workspaces,
    make_upload_document,
)


def make_config(api_key: str = "test-key") -> Config:
    return Config(
        base_url="http://anythingllm.test/api",
        api_key=api_key,
        workspace_slug="default-ws",
        mcp_host="127.0.0.1",
        mcp_port=8000,
        mcp_path="/mcp",
        request_timeout=5.0,
    )


def run(coro):
    return asyncio.run(coro)


def text_of(result) -> str:
    return result.content[0].text


class FakeClient:
    def __init__(self, **results):
        self.results = results
        self.calls = []
        self.error = None

    async def _answer(self, name, *args):
        self.calls.append((name, args))
        if self.error:
            raise self.error
        return self.results[name]

    async def chat(self, *args):
        return await self._answer("chat", *args)

    async def list_workspaces(self):
        return await self._answer("list_workspaces")

    async def create_workspace(self, *args):
        return await self._answer("create_workspace", *args)

    async def upload_document(self, *args):
        return await self._answer("upload_document", *args)


def test_ask_workspace_returns_answer_and_sources():
    client = FakeClient(chat={"textResponse": "42", "sources": [{"title": "x"}]})
    tool = make_ask_workspace(make_config(), client)

    result = run(tool("meaning of life"))

    assert text_of(result) == "42"
    assert result.structured_content["sources"] == [{"title": "x"}]
    assert client.calls == [("chat", ("default-ws", "meaning of life", "query"))]


def test_ask_workspace_rejects_empty_message():
    client = FakeClient(chat={})
    tool = make_ask_workspace(make_config(), client)

    result = run(tool("   "))

    assert result.is_error
    assert client.calls == []


def test_ask_workspace_reports_client_error():
    client = FakeClient(chat={})
    client.error = AnythingLLMError("backend down")
    tool = make_ask_workspace(make_config(), client)

    result = run(tool("hello"))

    assert result.is_error
    assert "backend down" in text_of(result)


def test_list_workspaces_formats_names_and_slugs():
    client = FakeClient(
        list_workspaces=[{"name": "育儿", "slug": "parenting"}, {"slug": "anon"}]
    )
    tool = make_list_workspaces(client)

    result = run(tool())

    assert "育儿" in text_of(result)
    assert "parenting" in text_of(result)
    assert "(未命名)" in text_of(result)
    assert result.structured_content["workspaces"] == [
        {"name": "育儿", "slug": "parenting"},
        {"name": "(未命名)", "slug": "anon"},
    ]


def test_list_workspaces_empty():
    tool = make_list_workspaces(FakeClient(list_workspaces=[]))

    assert "没有任何工作区" in text_of(run(tool()))


def test_create_workspace_returns_slug():
    client = FakeClient(create_workspace={"name": "Docs", "slug": "docs-1"})
    tool = make_create_workspace(client)

    result = run(tool("Docs"))

    assert "docs-1" in text_of(result)
    assert client.calls == [("create_workspace", ("Docs",))]


def test_create_workspace_requires_name():
    client = FakeClient(create_workspace={})
    tool = make_create_workspace(client)

    result = run(tool("  "))

    assert result.is_error
    assert client.calls == []


def test_upload_document_uses_default_workspace():
    client = FakeClient(
        upload_document={
            "success": True,
            "documents": [{"location": "custom-documents/a.txt"}],
        }
    )
    tool = make_upload_document(make_config(), client)

    result = run(tool("a.txt"))

    assert client.calls == [("upload_document", ("a.txt", "default-ws"))]
    assert "custom-documents/a.txt" in text_of(result)
    assert result.structured_content == {
        "workspace": "default-ws",
        "documents": ["custom-documents/a.txt"],
    }


def test_upload_document_explicit_workspace_wins():
    client = FakeClient(upload_document={"success": True, "documents": []})
    tool = make_upload_document(make_config(), client)

    run(tool("a.txt", "other-ws"))

    assert client.calls == [("upload_document", ("a.txt", "other-ws"))]


def test_create_server_requires_api_key():
    with pytest.raises(ConfigError, match="ANYTHINGLLM_API_KEY"):
        create_server(make_config(api_key="  "))
