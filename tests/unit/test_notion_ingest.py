from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import notion_ingest
from app.models.notion_ingest import (
    NotionDelivery,
    NotionIngestEvent,
    NotionSelectOptionMapping,
)
from app.schemas.notion_ingest import NotionDatabaseMappingUpsert, NotionIngestRequest
from app.services.notion_ingest import MappingValidationError, mapper_for_business_type, parse_mapping
from app.workers import notion_delivery


def exercise_properties(**overrides):
    properties = {
        "运动类型": {
            "type": "select",
            "select": {
                "id": "notion-option-id",
                "name": "跑步",
                "color": "blue",
            },
        },
        "月份": {
            "type": "title",
            "title": [{"type": "text", "text": {"content": "09月"}}],
        },
        "城市": {
            "type": "rich_text",
            "rich_text": [{"type": "text", "text": {"content": "上海市"}}],
        },
        "时长": {"type": "number", "number": 1},
        "记录时间": {
            "type": "date",
            "date": {"start": "2026-09-02T16:01:35+08:00"},
        },
        "日期": {"type": "date", "date": {"start": "2026-09-02"}},
    }
    properties.update(overrides)
    return properties


def notion_request(**overrides) -> NotionIngestRequest:
    body = {
        "parent": {"type": "database_id", "database_id": "exercise-db"},
        "properties": exercise_properties(),
    }
    body.update(overrides)
    return NotionIngestRequest(**body)


def test_exercise_mapper_parses_standard_notion_properties() -> None:
    parsed = parse_mapping("exercise_notion_v1", exercise_properties())

    assert parsed["sport_type_option_id"] == "notion-option-id"
    assert parsed["duration"] == 1.0
    assert parsed["occurred_at"].isoformat() == "2026-09-02T16:01:35+08:00"
    assert parsed["occurred_on"].isoformat() == "2026-09-02"
    assert parsed["city"] == "上海市"


def test_business_type_selects_the_current_mapper() -> None:
    assert mapper_for_business_type("exercise") == "exercise_notion_v1"


def test_exercise_mapper_rejects_invalid_mapped_input() -> None:
    with pytest.raises(MappingValidationError, match="时长"):
        parse_mapping(
            "exercise_notion_v1",
            exercise_properties(**{"时长": {"type": "number", "number": -1}}),
        )


def test_exercise_mapper_accepts_option_id_as_shortcut_name() -> None:
    parsed = parse_mapping(
        "exercise_notion_v1",
        exercise_properties(
            **{
                "运动类型": {
                    "type": "select",
                    "select": {
                        "id": "bb05a747-00a6-4c18-b7a2-32f834563dd6",
                        "name": "bb05a747-00a6-4c18-b7a2-32f834563dd6",
                        "color": "blue",
                    },
                }
            }
        ),
    )

    assert parsed["sport_type_option_id"] == "bb05a747-00a6-4c18-b7a2-32f834563dd6"


def test_exercise_mapper_rejects_missing_option_id() -> None:
    with pytest.raises(MappingValidationError, match="select.id"):
        parse_mapping(
            "exercise_notion_v1",
            exercise_properties(
                **{
                    "运动类型": {
                        "type": "select",
                        "select": {
                            "name": "跑步",
                            "color": "blue",
                        },
                    }
                }
            ),
        )


def test_notion_payload_preserves_extra_notion_page_fields() -> None:
    request = notion_request(children=[{"object": "block", "type": "paragraph"}])

    assert request.notion_payload() == {
        "parent": {"type": "database_id", "database_id": "exercise-db"},
        "properties": exercise_properties(),
        "children": [{"object": "block", "type": "paragraph"}],
    }


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def first(self):
        return self.result

    def one(self):
        return self.result

    def order_by(self, *args):
        return self

    def all(self):
        return self.result


class FakeDB:
    def __init__(self, mapping=None, sport_type_mapping=None):
        self.mapping = mapping
        self.sport_type_mapping = sport_type_mapping
        self.added = []
        self.committed = False

    def query(self, model):
        if model is NotionSelectOptionMapping:
            return FakeQuery(self.sport_type_mapping)
        return FakeQuery(self.mapping)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        for item in self.added:
            if isinstance(item, NotionIngestEvent) and item.id is None:
                item.id = uuid4()

    def commit(self):
        self.committed = True

    def refresh(self, item):
        if item.id is None:
            item.id = uuid4()

    def rollback(self):
        raise AssertionError("不应回滚")


@pytest.mark.asyncio
async def test_unmapped_event_is_persisted_and_queued() -> None:
    db = FakeDB()

    result = await notion_ingest.ingest_notion_page(
        request_in=notion_request(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.business_type is None
    assert result.mapping_name is None
    assert result.delivery_status == "pending"
    assert {type(item) for item in db.added} == {NotionIngestEvent, NotionDelivery}
    assert db.committed


@pytest.mark.asyncio
async def test_invalid_mapped_event_is_rejected_before_writes() -> None:
    db = FakeDB(
        mapping=SimpleNamespace(
            business_type="exercise",
            display_name="日常运动记录",
            mapper_key="exercise_notion_v1",
        ),
        sport_type_mapping=SimpleNamespace(name="跑步"),
    )

    with pytest.raises(HTTPException) as error:
        await notion_ingest.ingest_notion_page(
            request_in=notion_request(
                properties=exercise_properties(**{"时长": {"type": "number", "number": -1}})
            ),
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert error.value.status_code == 422
    assert db.added == []


@pytest.mark.asyncio
async def test_mapped_exercise_event_writes_event_delivery_and_record() -> None:
    db = FakeDB(
        mapping=SimpleNamespace(
            business_type="exercise",
            display_name="日常运动记录",
            mapper_key="exercise_notion_v1",
        ),
        sport_type_mapping=SimpleNamespace(name="跑步"),
    )

    result = await notion_ingest.ingest_notion_page(
        request_in=notion_request(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.business_type == "exercise"
    assert result.mapping_name == "日常运动记录"
    assert {type(item).__name__ for item in db.added} == {
        "NotionIngestEvent",
        "NotionDelivery",
        "SportRecord",
    }
    sport_record = next(item for item in db.added if type(item).__name__ == "SportRecord")
    assert sport_record.sport_type == "跑步"


@pytest.mark.asyncio
async def test_mapped_exercise_event_rejects_unknown_sport_type_option() -> None:
    db = FakeDB(
        mapping=SimpleNamespace(
            business_type="exercise",
            display_name="日常运动记录",
            mapper_key="exercise_notion_v1",
        )
    )

    with pytest.raises(HTTPException) as error:
        await notion_ingest.ingest_notion_page(
            request_in=notion_request(),
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert error.value.status_code == 422
    assert "未配置运动类型" in error.value.detail
    assert db.added == []


@pytest.mark.asyncio
async def test_mapping_upsert_creates_and_updates_mapping() -> None:
    new_db = FakeDB()
    body = NotionDatabaseMappingUpsert(
        business_type="exercise",
        display_name="日常运动记录",
        description="iOS 快捷指令提交；时长单位为小时。",
    )

    created = await notion_ingest.upsert_mapping(
        mapping_in=body,
        database_id="exercise-db",
        db=new_db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert created.notion_database_id == "exercise-db"
    assert created.business_type == "exercise"
    assert created.display_name == "日常运动记录"
    assert created.description == "iOS 快捷指令提交；时长单位为小时。"
    assert new_db.committed

    mapping = SimpleNamespace(
        business_type="other",
        display_name="旧名称",
        description=None,
        mapper_key="other",
    )
    existing_db = FakeDB(mapping=mapping)
    updated = await notion_ingest.upsert_mapping(
        mapping_in=body,
        database_id="exercise-db",
        db=existing_db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert updated.business_type == "exercise"
    assert updated.display_name == "日常运动记录"
    assert updated.mapper_key == "exercise_notion_v1"
    assert existing_db.added == []


@pytest.mark.asyncio
async def test_list_mappings_returns_current_user_rows() -> None:
    mappings = [
        SimpleNamespace(
            notion_database_id="a",
            business_type="exercise",
            display_name="日常运动记录",
            description="说明",
            mapper_key="exercise_notion_v1",
        )
    ]
    db = FakeDB(mapping=mappings)

    assert await notion_ingest.list_mappings(
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    ) == mappings


@pytest.mark.asyncio
async def test_delivery_worker_marks_success(monkeypatch) -> None:
    delivery = SimpleNamespace(
        id=uuid4(),
        notion_payload={"parent": {}, "properties": {}},
        attempt_count=0,
        status=NotionDelivery.STATUS_PROCESSING,
        locked_until=1,
        notion_page_id=None,
        last_error=None,
    )
    db = MagicMock()
    db.get.return_value = delivery
    monkeypatch.setattr(notion_delivery, "SessionLocal", lambda: db)
    monkeypatch.setattr(notion_delivery, "_claim_delivery", lambda _: delivery)
    monkeypatch.setattr(notion_delivery.settings, "NOTION_TOKEN", "server-token")
    from app.services import notion

    monkeypatch.setattr(
        notion,
        "NotionService",
        lambda _: SimpleNamespace(create_page_from_payload=AsyncMock(return_value="page-id")),
    )

    assert await notion_delivery.deliver_one()
    assert delivery.status == NotionDelivery.STATUS_SUCCEEDED
    assert delivery.notion_page_id == "page-id"
    assert delivery.attempt_count == 1
    db.commit.assert_called_once()
    db.close.assert_called_once()


def test_claim_delivery_locks_pending_record(monkeypatch) -> None:
    delivery = SimpleNamespace(status="pending", locked_until=None)
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value.order_by.return_value.with_for_update.return_value.first.return_value = delivery
    monkeypatch.setattr(notion_delivery, "_now", lambda: 100)
    monkeypatch.setattr(notion_delivery.settings, "NOTION_DELIVERY_LEASE_SECONDS", 30)

    assert notion_delivery._claim_delivery(db) is delivery
    assert delivery.status == NotionDelivery.STATUS_PROCESSING
    assert delivery.locked_until == 130
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delivery_worker_requeues_retry(monkeypatch) -> None:
    delivery = SimpleNamespace(
        id=uuid4(),
        notion_payload={"parent": {}, "properties": {}},
        attempt_count=0,
        status=NotionDelivery.STATUS_PROCESSING,
        locked_until=1,
        notion_page_id=None,
        last_error=None,
        next_attempt_at=0,
    )
    db = MagicMock()
    db.get.return_value = delivery
    monkeypatch.setattr(notion_delivery, "SessionLocal", lambda: db)
    monkeypatch.setattr(notion_delivery, "_claim_delivery", lambda _: delivery)
    monkeypatch.setattr(notion_delivery, "_now", lambda: 100)
    monkeypatch.setattr(notion_delivery.settings, "NOTION_TOKEN", "server-token")
    monkeypatch.setattr(notion_delivery.settings, "NOTION_DELIVERY_RETRY_DELAY_SECONDS", 30)
    from app.services import notion

    monkeypatch.setattr(
        notion,
        "NotionService",
        lambda _: SimpleNamespace(create_page_from_payload=AsyncMock(return_value=None)),
    )

    assert await notion_delivery.deliver_one()
    assert delivery.status == NotionDelivery.STATUS_PENDING
    assert delivery.next_attempt_at == 130
    assert delivery.attempt_count == 1


@pytest.mark.asyncio
async def test_delivery_worker_skips_when_notion_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(notion_delivery.settings, "NOTION_TOKEN", None)

    assert not await notion_delivery.deliver_one()


@pytest.mark.asyncio
async def test_delivery_worker_marks_final_failure(monkeypatch) -> None:
    delivery = SimpleNamespace(
        id=uuid4(),
        notion_payload={"parent": {}, "properties": {}},
        attempt_count=2,
        status=NotionDelivery.STATUS_PROCESSING,
        locked_until=1,
        notion_page_id=None,
        last_error=None,
    )
    db = MagicMock()
    db.get.return_value = delivery
    monkeypatch.setattr(notion_delivery, "SessionLocal", lambda: db)
    monkeypatch.setattr(notion_delivery, "_claim_delivery", lambda _: delivery)
    monkeypatch.setattr(notion_delivery.settings, "NOTION_TOKEN", "server-token")
    monkeypatch.setattr(notion_delivery.settings, "BARK_DEFAULT_DEVICE_KEY", None)
    from app.services import notion

    monkeypatch.setattr(
        notion,
        "NotionService",
        lambda _: SimpleNamespace(create_page_from_payload=AsyncMock(return_value=None)),
    )

    assert await notion_delivery.deliver_one()
    assert delivery.status == NotionDelivery.STATUS_FAILED
    assert delivery.attempt_count == 3
