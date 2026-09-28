"""list_pets MCP tool implementation."""

from __future__ import annotations

import logging
import time
from functools import partial
from typing import Any, Callable

from mcp.types import CallToolResult, TextContent

from ..config import Config
from ..errors import ErrorCode
from ..rest_client import (
    BackendApiError,
    BackendTimeout,
    BackendUnavailable,
    InvalidResponse,
    PetHospitalClient,
)
from .list_pets_models import ListPetsInput, ListPetsSuccess

logger = logging.getLogger(__name__)

TOOL_NAME = "list_pets"
TOOL_DESCRIPTION = (
    "查询宠物档案列表。支持按关键词、种类、主治医生、疾病、就诊状态、"
    "总花费区间筛选，可按任意字段升序/降序排序，支持分页。"
    "适用于：按条件检索档案、查看特定医生的接诊宠物、查询费用在某个区间的宠物等场景。"
    "返回分页后的宠物列表，包含每只宠物的基本信息、历史病历、消费明细和费用汇总。"
)


def _error_result(error_code: ErrorCode, message: str) -> CallToolResult:
    """Build a CallToolResult representing an error."""
    error_dict = {
        "error": {
            "code": error_code.value,
            "message": message,
            "details": {},
        }
    }
    return CallToolResult(
        content=[TextContent(type="text", text=str(error_dict))],
        structured_content=error_dict,
        is_error=True,
    )


def _make_tool_func(
    config: Config, client: PetHospitalClient
) -> Callable[[dict[str, Any]], Any]:
    """Create a tool function with config and client bound.

    The returned function accepts only `arguments: dict[str, Any]` so the
    MCP SDK can generate a clean JSON schema from ListPetsInput without
    seeing the Config / PetHospitalClient types.
    """

    async def tool_fn(arguments: dict[str, Any]) -> CallToolResult:
        start = time.monotonic()
        logger.info(
            "list_pets called",
            extra={
                "tool_name": TOOL_NAME,
                "params": arguments,
                "status": "started",
            },
        )

        # --- Validate input ---
        try:
            input_data = ListPetsInput.model_validate(arguments)
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets validation failed",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": arguments,
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            return _error_result(
                ErrorCode.VALIDATION_ERROR,
                f"Input validation failed: {exc}",
            )

        # --- Call backend ---
        try:
            raw_data = await client.list_pets(input_data.to_query_params())
        except BackendTimeout:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets backend timeout",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return _error_result(
                ErrorCode.BACKEND_TIMEOUT,
                "Backend request timed out",
            )
        except BackendUnavailable:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets backend unavailable",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return _error_result(
                ErrorCode.BACKEND_UNAVAILABLE,
                "Backend is unreachable",
            )
        except BackendApiError as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets backend API error",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                    "error": str(exc),
                },
            )
            return _error_result(
                ErrorCode.BACKEND_API_ERROR,
                f"Backend returned HTTP {exc.status_code}: {exc.message}",
            )
        except InvalidResponse as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets invalid response",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                    "error": str(exc),
                },
            )
            return _error_result(
                ErrorCode.BACKEND_INVALID_RESPONSE,
                f"Backend returned invalid response: {exc}",
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets internal error",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            return _error_result(
                ErrorCode.INTERNAL_ERROR,
                f"Internal error: {exc}",
            )

        # --- Parse and validate output ---
        try:
            success = ListPetsSuccess.model_validate(raw_data)
        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "list_pets output validation failed",
                extra={
                    "tool_name": TOOL_NAME,
                    "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            return _error_result(
                ErrorCode.BACKEND_INVALID_RESPONSE,
                f"Response validation failed: {exc}",
            )

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "list_pets success",
            extra={
                "tool_name": TOOL_NAME,
                "params": input_data.model_dump(by_alias=True, exclude_unset=True),
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
            },
        )

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Retrieved {success.total} pets (page {success.page}/{success.total_pages})",
                )
            ],
            structured_content=success.model_dump(by_alias=True),
        )

    return tool_fn


# Public interface used by tests
run_list_pets: Callable[[Config, PetHospitalClient, dict[str, Any]], Any] = (
    lambda config, client, arguments: _make_tool_func(config, client)(arguments)
)
