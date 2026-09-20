"""可选的公开请求调试接收器。"""

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Request


router = APIRouter()
logger = logging.getLogger(__name__)


def _header_items(request: Request) -> list[dict[str, str]]:
    """保留原始 header 的顺序与重复项，便于排查第三方回调。"""
    return [
        {
            "name": name.decode("latin-1"),
            "value": value.decode("latin-1"),
        }
        for name, value in request.scope["headers"]
    ]


@router.post(
    "/",
    summary="公开接收并回显原始 POST 请求",
    description="仅在 ENABLE_PUBLIC_REQUEST_DUMP=true 时注册；不校验认证或请求体。",
)
async def dump_public_request(request: Request) -> dict[str, Any]:
    """记录并回显未经业务校验的请求，供临时接口改造联调使用。"""
    raw_body = await request.body()
    payload: dict[str, Any] = {
        "method": request.method,
        "path": request.url.path,
        "query_params": [
            {"name": name, "value": value}
            for name, value in request.query_params.multi_items()
        ],
        "headers": _header_items(request),
        "client": {
            "host": request.client.host if request.client else None,
            "port": request.client.port if request.client else None,
        },
        "body": {
            "size_bytes": len(raw_body),
            "utf8_text": raw_body.decode("utf-8", errors="replace"),
            "base64": base64.b64encode(raw_body).decode("ascii"),
        },
    }
    logger.warning(
        "公开请求调试接收器收到请求：%s",
        json.dumps(payload, ensure_ascii=False),
    )
    return payload
