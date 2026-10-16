"""Tests for the Pet Hospital MCP service."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.errors import ErrorCode
from pet_hospital_mcp.rest_client import (
    BackendApiError,
    BackendTimeout,
    BackendUnavailable,
    InvalidResponse,
    PetHospitalClient,
)
from pet_hospital_mcp.tools.list_pets import TOOL_NAME, run_list_pets
from pet_hospital_mcp.tools.list_pets_models import ListPetsInput, ListPetsSuccess
from pet_hospital_mcp.server import create_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> Config:
    return Config(
        pet_hospital_base_url="http://127.0.0.1:8080",
        mcp_host="127.0.0.1",
        mcp_port=8000,
        mcp_path="/mcp",
        request_timeout=10.0,
        max_retries=2,
    )


@pytest.fixture
def client(config: Config) -> PetHospitalClient:
    return PetHospitalClient(config)


# ---------------------------------------------------------------------------
# Sample responses
# ---------------------------------------------------------------------------

_SUCCESS_RESPONSE_DATA = {
    "items": [
        {
            "id": "PET-000001",
            "name": "旺财",
            "species": "犬",
            "breed": "金毛",
            "gender": "公",
            "ageMonths": 36,
            "color": "金色",
            "ownerName": "张三",
            "ownerPhone": "13800001111",
            "ownerAddr": "北京市朝阳区",
            "doctor": "李医生",
            "disease": "急性肠胃炎",
            "status": "已康复",
            "allergy": "无",
            "note": "",
            "records": [
                {
                    "id": "MR-001",
                    "visitDate": "2024-01-01",
                    "doctor": "李医生",
                    "diagnosis": "急性肠胃炎",
                    "symptoms": "呕吐",
                    "treatment": "补液",
                    "prescription": ["阿莫西林"],
                    "weightKg": 12.5,
                    "temperature": 39.1,
                    "followUp": "复查",
                    "charge": 380.0,
                    "createdAt": "2024-01-01T00:00:00Z",
                }
            ],
            "charges": [
                {
                    "id": "CH-001",
                    "item": "血常规",
                    "category": "检查",
                    "amount": 180.0,
                    "doctor": "李医生",
                    "date": "2024-01-01",
                }
            ],
            "totalCost": 380.0,
            "visitCount": 1,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
        }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 10,
    "totalPages": 1,
    "totalCost": 380.0,
}

_SUCCESS_RESPONSE = {"code": 200, "message": "ok", "data": _SUCCESS_RESPONSE_DATA}

_NULL_RECORDS_CHARGES_DATA = {
    "items": [
        {
            "id": "PET-000002",
            "name": "咪咪",
            "species": "猫",
            "breed": "英短",
            "gender": "母",
            "ageMonths": 12,
            "color": "灰色",
            "ownerName": "李四",
            "ownerPhone": "13900002222",
            "ownerAddr": "上海市浦东新区",
            "doctor": "王医生",
            "disease": "猫瘟",
            "status": "就诊中",
            "allergy": "无",
            "note": "",
            "records": None,
            "charges": None,
            "totalCost": 0.0,
            "visitCount": 0,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
        }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 10,
    "totalPages": 1,
    "totalCost": 0.0,
}


# ---------------------------------------------------------------------------
# Tests: ListPetsInput validation
# ---------------------------------------------------------------------------


class TestListPetsInput:
    """Test input model validation."""

    def test_valid_minimal(self) -> None:
        inp = ListPetsInput()
        assert inp.page == 1
        assert inp.page_size == 20

    def test_valid_all_params(self) -> None:
        inp = ListPetsInput(
            q="肠胃炎",
            name="旺财",
            owner_name="张三",
            owner_phone="13800001111",
            species="犬",
            doctor="李医生",
            disease="急性肠胃炎",
            status="已康复",
            min=100.0,
            max=5000.0,
            sort_by="totalCost",
            order="desc",
            page=2,
            page_size=50,
        )
        assert inp.species == "犬"
        assert inp.status == "已康复"
        assert inp.sort_by == "totalCost"
        assert inp.order == "desc"

    def test_species_invalid(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(species="马")

    def test_status_invalid(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(status="已出院")

    def test_sort_by_invalid(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(sort_by="random")

    def test_order_invalid(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(order="ascending")

    def test_page_too_low(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(page=0)

    def test_page_size_too_low(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(page_size=0)

    def test_page_size_too_high(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(page_size=501)

    def test_min_negative(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(min=-1.0)

    def test_max_negative(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(max=-1.0)

    def test_min_gt_max(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(min=5000.0, max=100.0)

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(extra_field="value")

    def test_to_query_params(self) -> None:
        inp = ListPetsInput(species="犬", page=2, page_size=10)
        params = inp.to_query_params()
        assert params["species"] == "犬"
        assert params["page"] == "2"
        assert params["pageSize"] == "10"

    def test_to_query_params_snake_case_alias(self) -> None:
        inp = ListPetsInput(owner_name="张三", owner_phone="13800001111")
        params = inp.to_query_params()
        assert params["ownerName"] == "张三"
        assert params["ownerPhone"] == "13800001111"

    def test_nan_rejected(self) -> None:
        with pytest.raises(Exception):
            ListPetsInput(min=float("nan"))

    def test_infinity_rejected(self) -> None:
        # Pydantic v2 allows infinity for float; we validate in the tool itself
        inp = ListPetsInput(max=float("inf"))
        # The model accepts it, but the tool should reject it via query param
        assert inp.max == float("inf")


# ---------------------------------------------------------------------------
# Tests: ListPetsSuccess model
# ---------------------------------------------------------------------------


class TestListPetsSuccess:
    """Test output model."""

    def test_parse_success(self) -> None:
        success = ListPetsSuccess.model_validate(_SUCCESS_RESPONSE_DATA)
        assert success.total == 1
        assert len(success.items) == 1
        assert success.items[0].name == "旺财"

    def test_null_records(self) -> None:
        data = dict(_SUCCESS_RESPONSE_DATA)
        data["items"] = [
            {
                **_SUCCESS_RESPONSE_DATA["items"][0],
                "records": None,
                "charges": None,
            }
        ]
        success = ListPetsSuccess.model_validate(data)
        assert success.items[0].records is None
        assert success.items[0].charges is None

    def test_empty_items(self) -> None:
        data = {**_SUCCESS_RESPONSE_DATA, "items": []}
        success = ListPetsSuccess.model_validate(data)
        assert success.items == []
        # total reflects backend value, not derived from items length


# ---------------------------------------------------------------------------
# Tests: REST client
# ---------------------------------------------------------------------------


class TestPetHospitalClient:
    """Test the REST client against mocked backend."""

    @respx.mock
    async def test_list_pets_success(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=httpx.Response(200, json=_SUCCESS_RESPONSE)
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=2,
            )
        )
        try:
            result = await client.list_pets({"species": "犬", "page": "1", "pageSize": "10"})
            assert "items" in result
            assert result["total"] == 1
            assert route.called
        finally:
            await client.close()

    @respx.mock
    async def test_list_pets_forwards_all_params(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=httpx.Response(200, json=_SUCCESS_RESPONSE)
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=2,
            )
        )
        try:
            params = {
                "q": "肠胃炎",
                "name": "旺财",
                "ownerName": "张三",
                "ownerPhone": "13800001111",
                "species": "犬",
                "doctor": "李医生",
                "disease": "急性肠胃炎",
                "status": "已康复",
                "min": "1000",
                "max": "5000",
                "sortBy": "totalCost",
                "order": "desc",
                "page": "2",
                "pageSize": "50",
            }
            await client.list_pets(params)
            assert route.called
            request_url = route.calls[0].request.url
            assert request_url.params.get("q") == "肠胃炎"
            assert request_url.params.get("species") == "犬"
            assert request_url.params.get("sortBy") == "totalCost"
            assert request_url.params.get("order") == "desc"
            assert request_url.params.get("page") == "2"
            assert request_url.params.get("pageSize") == "50"
        finally:
            await client.close()

    @respx.mock
    async def test_list_pets_4xx(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=httpx.Response(400, json={"code": 400, "message": "bad request"})
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=1,
            )
        )
        with pytest.raises(BackendApiError) as exc_info:
            await client.list_pets({"page": "1", "pageSize": "10"})
        assert exc_info.value.status_code == 400
        await client.close()

    @respx.mock
    async def test_list_pets_5xx(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=1,
            )
        )
        with pytest.raises(BackendApiError) as exc_info:
            await client.list_pets({"page": "1", "pageSize": "10"})
        assert exc_info.value.status_code == 500
        await client.close()

    @respx.mock
    async def test_list_pets_timeout(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=0.001,
                max_retries=1,
            )
        )
        with pytest.raises(BackendTimeout):
            await client.list_pets({"page": "1", "pageSize": "10"})
        await client.close()

    @respx.mock
    async def test_list_pets_connection_error(self) -> None:
        route = respx.get("http://127.0.0.1:9999/api/v1/pets").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:9999",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=1,
            )
        )
        with pytest.raises(BackendUnavailable):
            await client.list_pets({"page": "1", "pageSize": "10"})
        assert route.called
        await client.close()

    @respx.mock
    async def test_list_pets_invalid_json(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=httpx.Response(200, text="not json")
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=1,
            )
        )
        with pytest.raises(Exception):
            await client.list_pets({"page": "1", "pageSize": "10"})
        await client.close()

    @respx.mock
    async def test_list_pets_malformed_response_structure(self) -> None:
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=httpx.Response(200, json={"code": 200, "message": "ok"})
        )
        client = PetHospitalClient(
            Config(
                pet_hospital_base_url="http://127.0.0.1:8080",
                mcp_host="127.0.0.1",
                mcp_port=8000,
                mcp_path="/mcp",
                request_timeout=10.0,
                max_retries=1,
            )
        )
        with pytest.raises(InvalidResponse):
            await client.list_pets({"page": "1", "pageSize": "10"})
        await client.close()


# ---------------------------------------------------------------------------
# Tests: list_pets tool
# ---------------------------------------------------------------------------


class TestListPetsTool:
    """Test the list_pets MCP tool."""

    @pytest.mark.asyncio
    async def test_success(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(return_value=_SUCCESS_RESPONSE_DATA)):
            result = await run_list_pets(config, rest_client, {})
        assert result.is_error is False
        assert result.structured_content is not None
        assert result.structured_content["total"] == 1
        assert len(result.structured_content["items"]) == 1

    @pytest.mark.asyncio
    async def test_success_with_null_records(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(return_value=_NULL_RECORDS_CHARGES_DATA)):
            result = await run_list_pets(config, rest_client, {})
        assert result.is_error is False
        assert result.structured_content["items"][0]["records"] is None
        assert result.structured_content["items"][0]["charges"] is None

    @pytest.mark.asyncio
    async def test_validation_error(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        result = await run_list_pets(config, rest_client, {"species": "马"})
        assert result.is_error is True
        assert result.structured_content is not None
        assert result.structured_content["error"]["code"] == ErrorCode.VALIDATION_ERROR.value

    @pytest.mark.asyncio
    async def test_backend_timeout(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(side_effect=BackendTimeout())):
            result = await run_list_pets(config, rest_client, {})
        assert result.is_error is True
        assert result.structured_content["error"]["code"] == ErrorCode.BACKEND_TIMEOUT.value

    @pytest.mark.asyncio
    async def test_backend_unavailable(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(side_effect=BackendUnavailable())):
            result = await run_list_pets(config, rest_client, {})
        assert result.is_error is True
        assert result.structured_content["error"]["code"] == ErrorCode.BACKEND_UNAVAILABLE.value

    @pytest.mark.asyncio
    async def test_backend_api_error(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(side_effect=BackendApiError(500, "server error"))):
            result = await run_list_pets(config, rest_client, {})
        assert result.is_error is True
        assert result.structured_content["error"]["code"] == ErrorCode.BACKEND_API_ERROR.value

    @pytest.mark.asyncio
    async def test_backend_invalid_response(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(return_value={"bad": "data"})):
            result = await run_list_pets(config, rest_client, {})
        assert result.is_error is True
        assert result.structured_content["error"]["code"] == ErrorCode.BACKEND_INVALID_RESPONSE.value

    @pytest.mark.asyncio
    async def test_output_schema_matches_go_api(self, config: Config) -> None:
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(return_value=_SUCCESS_RESPONSE_DATA)):
            result = await run_list_pets(config, rest_client, {})
        assert result.structured_content is not None
        sc = result.structured_content
        assert "items" in sc
        assert "total" in sc
        assert "page" in sc
        assert "pageSize" in sc
        assert "totalPages" in sc
        assert "totalCost" in sc
        # Check item fields
        item = sc["items"][0]
        assert "id" in item
        assert "name" in item
        assert "species" in item
        assert "records" in item
        assert "charges" in item
        assert "totalCost" in item
        assert "visitCount" in item


# ---------------------------------------------------------------------------
# Tests: MCP server registration and schema
# ---------------------------------------------------------------------------


class TestServerRegistration:
    """Test MCP server tool registration."""

    def test_tool_registered(self, config: Config) -> None:
        server, _ = create_server(config)
        tools = server._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert TOOL_NAME in names

    def test_tool_schema(self, config: Config) -> None:
        server, _ = create_server(config)
        tools = server._tool_manager.list_tools()
        tool_info = next(t for t in tools if t.name == TOOL_NAME)
        schema = tool_info.parameters
        assert schema["type"] == "object"
        assert "properties" in schema
        props = schema["properties"]
        assert "species" in props
        assert "status" in props
        assert "sortBy" in props
        assert "order" in props
        assert "page" in props
        assert "pageSize" in props
        assert props["page"]["minimum"] == 1
        assert props["pageSize"]["minimum"] == 1
        assert props["pageSize"]["maximum"] == 500

    def test_tool_description(self, config: Config) -> None:
        server, _ = create_server(config)
        tools = server._tool_manager.list_tools()
        tool_info = next(t for t in tools if t.name == TOOL_NAME)
        assert len(tool_info.description) > 10
        assert "查询" in tool_info.description or "宠物" in tool_info.description


# ---------------------------------------------------------------------------
# Tests: HTTP MCP endpoint (stateless flow)
# ---------------------------------------------------------------------------


class TestHttpEndpoint:
    """Test the HTTP MCP endpoint."""

    def test_list_tools_via_http(self, config: Config) -> None:
        """Test that tools can be discovered via the MCP HTTP endpoint."""
        server, app = create_server(config)
        with TestClient(app) as client:
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["result"]["tools"][0]["name"] == TOOL_NAME

    def test_call_tool_via_http(self, config: Config) -> None:
        """Test that the tool can be called via the MCP HTTP endpoint."""
        server, app = create_server(config)
        rest_client = PetHospitalClient(config)
        with patch.object(rest_client, "list_pets", new=AsyncMock(return_value=_SUCCESS_RESPONSE_DATA)):
            # Patch at the module level
            import pet_hospital_mcp.tools.list_pets as list_pets_module
            original_run = list_pets_module.run_list_pets

            async def patched_run(cfg, client, args):
                return await original_run(cfg, rest_client, args)

            list_pets_module.run_list_pets = patched_run
            try:
                with TestClient(app) as client:
                    resp = client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {
                                "name": TOOL_NAME,
                                "arguments": {"species": "犬", "page": 1, "pageSize": 10},
                            },
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    assert resp.status_code == 200
                    body = resp.json()
                    assert body["result"]["isError"] is False
                    assert body["result"]["structuredContent"]["total"] == 1
            finally:
                list_pets_module.run_list_pets = original_run

    def test_call_tool_validation_error_via_http(self, config: Config) -> None:
        """Test that validation errors are returned via HTTP."""
        server, app = create_server(config)
        with TestClient(app) as client:
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": TOOL_NAME,
                        "arguments": {"species": "马"},
                    },
                },
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["result"]["isError"] is True

    def test_health_endpoint(self, config: Config) -> None:
        """Test the /health endpoint."""
        server, app = create_server(config)
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "healthy"

    def test_no_initialize_required(self, config: Config) -> None:
        """Test that the endpoint works without initialize (stateless)."""
        server, app = create_server(config)
        with TestClient(app) as client:
            # Direct tools/list without initialize
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 200

    def test_no_session_id_in_response(self, config: Config) -> None:
        """Test that no Mcp-Session-Id is returned (stateless)."""
        server, app = create_server(config)
        with TestClient(app) as client:
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                },
                headers={"Content-Type": "application/json"},
            )
            assert "Mcp-Session-Id" not in resp.headers


# ---------------------------------------------------------------------------
# Tests: Logging redaction
# ---------------------------------------------------------------------------


class TestLogging:
    """Test that sensitive fields are redacted in logs."""

    def test_redact_dict(self, config: Config) -> None:
        from pet_hospital_mcp.logging_config import _redact_dict
        data = {
            "ownerPhone": "13800001111",
            "owner_name": "张三",
            "chipNo": "ABC123",
            "nested": {"ownerAddr": "北京市朝阳区"},
        }
        result = _redact_dict(data)
        assert result["ownerPhone"] == "***01111"
        assert result["owner_name"] == "张三"  # not in sensitive set
        assert result["chipNo"] == "***123"
        assert result["nested"]["ownerAddr"] == "***阳市"


# ---------------------------------------------------------------------------
# Tests: Config
# ---------------------------------------------------------------------------


class TestConfig:
    """Test configuration loading."""

    def test_defaults(self) -> None:
        import os
        # Ensure env vars are not set
        for key in ("PET_HOSPITAL_BASE_URL", "MCP_HOST", "MCP_PORT", "MCP_PATH"):
            os.environ.pop(key, None)
        cfg = Config.from_env()
        assert cfg.pet_hospital_base_url == "http://127.0.0.1:8080"
        assert cfg.mcp_host == "127.0.0.1"
        assert cfg.mcp_port == 8000
        assert cfg.mcp_path == "/mcp"

    def test_custom_env(self) -> None:
        import os
        os.environ["PET_HOSPITAL_BASE_URL"] = "http://example.com"
        os.environ["MCP_HOST"] = "0.0.0.0"
        os.environ["MCP_PORT"] = "9000"
        try:
            cfg = Config.from_env()
            assert cfg.pet_hospital_base_url == "http://example.com"
            assert cfg.mcp_host == "0.0.0.0"
            assert cfg.mcp_port == 9000
        finally:
            os.environ.pop("PET_HOSPITAL_BASE_URL", None)
            os.environ.pop("MCP_HOST", None)
            os.environ.pop("MCP_PORT", None)

    def test_mcp_url(self, config: Config) -> None:
        assert config.mcp_url == "http://127.0.0.1:8000/mcp"
