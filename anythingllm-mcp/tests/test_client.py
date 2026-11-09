import asyncio
import json

import httpx
import pytest

from anythingllm_mcp.client import AnythingLLMClient, AnythingLLMError
from anythingllm_mcp.config import Config


def make_config() -> Config:
    return Config(
        base_url="http://anythingllm.test/api",
        api_key="test-key",
        workspace_slug="default-ws",
        mcp_host="127.0.0.1",
        mcp_port=8000,
        mcp_path="/mcp",
        request_timeout=5.0,
    )


def make_client(handler) -> AnythingLLMClient:
    return AnythingLLMClient(
        make_config(), transport=httpx.MockTransport(handler)
    )


def run(coro):
    return asyncio.run(coro)


def test_list_workspaces_returns_workspaces():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/workspaces"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200, json={"workspaces": [{"name": "A", "slug": "a"}, "junk"]}
        )

    client = make_client(handler)
    try:
        workspaces = run(client.list_workspaces())
    finally:
        run(client.close())
    assert workspaces == [{"name": "A", "slug": "a"}]


def test_create_workspace_posts_name():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"workspace": {"name": "New", "slug": "new-slug"}}
        )

    client = make_client(handler)
    try:
        workspace = run(client.create_workspace("New"))
    finally:
        run(client.close())
    assert workspace["slug"] == "new-slug"
    assert seen["path"] == "/api/v1/workspace/new"
    assert seen["body"] == {"name": "New"}


def test_upload_document_sends_file_and_workspace(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        body = request.content
        seen["body"] = body
        return httpx.Response(
            200,
            json={
                "success": True,
                "documents": [{"location": "custom-documents/notes.txt"}],
            },
        )

    client = make_client(handler)
    try:
        payload = run(client.upload_document(str(source), "default-ws"))
    finally:
        run(client.close())

    assert seen["path"] == "/api/v1/document/upload"
    assert b'name="addToWorkspaces"' in seen["body"]
    assert b"default-ws" in seen["body"]
    assert b'filename="notes.txt"' in seen["body"]
    assert b"hello" in seen["body"]
    assert payload["documents"][0]["location"] == "custom-documents/notes.txt"


def test_upload_document_without_workspace_omits_field(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"success": True, "documents": []})

    client = make_client(handler)
    try:
        run(client.upload_document(str(source)))
    finally:
        run(client.close())

    assert b"addToWorkspaces" not in seen["body"]


def test_upload_missing_file_raises():
    client = make_client(lambda request: httpx.Response(200, json={}))
    try:
        with pytest.raises(AnythingLLMError, match="无法读取文件"):
            run(client.upload_document("definitely-missing.txt"))
    finally:
        run(client.close())


def test_http_error_is_reported():
    client = make_client(
        lambda request: httpx.Response(401, text="No api key")
    )
    try:
        with pytest.raises(AnythingLLMError, match="HTTP 401"):
            run(client.list_workspaces())
    finally:
        run(client.close())


def test_body_error_is_reported():
    client = make_client(
        lambda request: httpx.Response(200, json={"error": "bad things"})
    )
    try:
        with pytest.raises(AnythingLLMError, match="bad things"):
            run(client.chat("ws", "hi", "query"))
    finally:
        run(client.close())


def test_timeout_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    try:
        with pytest.raises(AnythingLLMError, match="timed out"):
            run(client.chat("ws", "hi", "query"))
    finally:
        run(client.close())


def test_unexpected_payload_is_reported():
    client = make_client(
        lambda request: httpx.Response(200, json={"workspaces": "nope"})
    )
    try:
        with pytest.raises(AnythingLLMError, match="unexpected"):
            run(client.list_workspaces())
    finally:
        run(client.close())
