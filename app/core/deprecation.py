"""废弃功能的统一保护机制。"""

from fastapi import APIRouter, Depends, HTTPException, status


def create_disabled_router(feature_name: str) -> APIRouter:
    """创建一个即使被误注册也只返回 410 的废弃路由。"""

    async def reject_deprecated_feature() -> None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"{feature_name}已废弃并禁止调用",
        )

    return APIRouter(
        deprecated=True,
        dependencies=[Depends(reject_deprecated_feature)],
    )
