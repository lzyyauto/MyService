from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.security import get_current_user
from app.schemas.rest_record import RestRecordCreate, to_cn_timezone


@pytest.mark.asyncio
async def test_missing_credentials_returns_401() -> None:
    with pytest.raises(HTTPException) as error:
        await get_current_user(credentials=None, db=MagicMock())

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_api_key_returns_user() -> None:
    user = SimpleNamespace(id="user-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    result = await get_current_user(
        credentials=SimpleNamespace(credentials="valid-key"),
        db=db,
    )

    assert result is user


def test_rest_type_rejects_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        RestRecordCreate(rest_type=2)


def test_timestamp_is_converted_to_china_timezone() -> None:
    converted = to_cn_timezone(0)

    assert converted.isoformat() == "1970-01-01T08:00:00+08:00"
