"""接收 iOS 快捷指令产生的 Notion 标准页面载荷。"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.notion_ingest import (
    NotionDatabaseMapping,
    NotionDelivery,
    NotionIngestEvent,
    NotionSelectOptionMapping,
    SportRecord,
)
from app.models.user import User
from app.schemas.notion_ingest import (
    NotionDatabaseMappingResponse,
    NotionDatabaseMappingUpsert,
    NotionIngestRequest,
    NotionIngestResponse,
)
from app.services.notion_ingest import (
    MappingValidationError,
    mapper_for_business_type,
    parse_mapping,
)

router = APIRouter()


def _mapping_for_user(
    db: Session,
    user_id: str,
    database_id: str,
) -> NotionDatabaseMapping | None:
    return (
        db.query(NotionDatabaseMapping)
        .filter(
            NotionDatabaseMapping.user_id == user_id,
            NotionDatabaseMapping.notion_database_id == database_id,
        )
        .first()
    )


@router.put(
    "/mappings/{database_id}",
    response_model=NotionDatabaseMappingResponse,
    summary="设置 Notion database 的本地业务映射",
)
async def upsert_mapping(
    mapping_in: NotionDatabaseMappingUpsert,
    database_id: str = Path(..., min_length=1, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotionDatabaseMappingResponse:
    mapper_key = mapper_for_business_type(mapping_in.business_type)
    mapping = _mapping_for_user(db, current_user.id, database_id)
    if mapping is None:
        mapping = NotionDatabaseMapping(
            user_id=current_user.id,
            notion_database_id=database_id,
            business_type=mapping_in.business_type,
            display_name=mapping_in.display_name,
            description=mapping_in.description,
            mapper_key=mapper_key,
        )
        db.add(mapping)
    else:
        mapping.business_type = mapping_in.business_type
        mapping.display_name = mapping_in.display_name
        mapping.description = mapping_in.description
        mapping.mapper_key = mapper_key
    db.commit()
    return mapping


@router.get(
    "/mappings",
    response_model=List[NotionDatabaseMappingResponse],
    summary="列出当前用户的 Notion database 映射",
)
async def list_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[NotionDatabaseMapping]:
    return (
        db.query(NotionDatabaseMapping)
        .filter(NotionDatabaseMapping.user_id == current_user.id)
        .order_by(NotionDatabaseMapping.notion_database_id.asc())
        .all()
    )


@router.post(
    "/",
    response_model=NotionIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="接收 Notion 标准页面载荷并异步同步",
)
async def ingest_notion_page(
    request_in: NotionIngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotionIngestResponse:
    database_id = request_in.parent.database_id
    if request_in.idempotency_key:
        existing = (
            db.query(NotionIngestEvent)
            .filter(
                NotionIngestEvent.user_id == current_user.id,
                NotionIngestEvent.idempotency_key == request_in.idempotency_key,
            )
            .first()
        )
        if existing is not None:
            delivery = (
                db.query(NotionDelivery)
                .filter(NotionDelivery.event_id == existing.id)
                .one()
            )
            return NotionIngestResponse(
                event_id=existing.id,
                delivery_id=delivery.id,
                business_type=existing.business_type,
                mapping_name=existing.mapping_display_name,
                delivery_status=delivery.status,
                duplicate=True,
            )

    mapping = _mapping_for_user(db, current_user.id, database_id)
    parsed_record: dict | None = None
    if mapping is not None:
        try:
            parsed_record = parse_mapping(mapping.mapper_key, request_in.properties)
        except MappingValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        sport_type_option_id = parsed_record.pop("sport_type_option_id")
        sport_type_mapping = (
            db.query(NotionSelectOptionMapping)
            .filter(NotionSelectOptionMapping.option_id == sport_type_option_id)
            .first()
        )
        if sport_type_mapping is None:
            raise HTTPException(
                status_code=422,
                detail=f"未配置运动类型选项 ID “{sport_type_option_id}” 的名称映射",
            )
        parsed_record["sport_type"] = sport_type_mapping.name

    event = NotionIngestEvent(
        user_id=current_user.id,
        notion_database_id=database_id,
        idempotency_key=request_in.idempotency_key,
        business_type=mapping.business_type if mapping else None,
        mapping_display_name=mapping.display_name if mapping else None,
        mapper_key=mapping.mapper_key if mapping else None,
        original_payload=request_in.model_dump(mode="json"),
    )
    delivery = NotionDelivery(
        notion_payload=request_in.notion_payload(),
        status=NotionDelivery.STATUS_PENDING,
    )
    try:
        db.add(event)
        db.flush()
        delivery.event_id = event.id
        db.add(delivery)
        if parsed_record is not None:
            db.add(
                SportRecord(
                    user_id=current_user.id,
                    source_event_id=event.id,
                    **parsed_record,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(event)
    db.refresh(delivery)
    return NotionIngestResponse(
        event_id=event.id,
        delivery_id=delivery.id,
        business_type=event.business_type,
        mapping_name=event.mapping_display_name,
        delivery_status=delivery.status,
    )
