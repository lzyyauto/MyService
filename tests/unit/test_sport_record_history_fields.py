from app.models.notion_ingest import SportRecord
from app.schemas.dashboard import SportRecordItem


def test_sport_record_retains_history_fields_without_exposing_them() -> None:
    assert {"detail", "detail2"}.issubset(SportRecord.__table__.columns.keys())
    assert "detail" not in SportRecordItem.model_fields
    assert "detail2" not in SportRecordItem.model_fields
