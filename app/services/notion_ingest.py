"""已知 Notion database 映射的严格解析器。"""

from datetime import date, datetime
from typing import Any

MAPPER_EXERCISE_NOTION_V1 = "exercise_notion_v1"
BUSINESS_TYPE_EXERCISE = "exercise"


def mapper_for_business_type(business_type: str) -> str:
    """选择一个业务类型当前绑定的严格解析规则。"""
    if business_type == BUSINESS_TYPE_EXERCISE:
        return MAPPER_EXERCISE_NOTION_V1
    raise ValueError(f"不支持的业务类型：{business_type}")


class MappingValidationError(ValueError):
    """已配置映射的载荷不符合该业务契约。"""


def _required_property(
    properties: dict[str, dict[str, Any]],
    name: str,
    property_type: str,
) -> dict[str, Any]:
    value = properties.get(name)
    if not isinstance(value, dict) or value.get("type") != property_type:
        raise MappingValidationError(f"属性“{name}”必须是 {property_type} 类型")
    return value


def _text_content(item: dict[str, Any], name: str) -> str:
    text = item.get("text")
    content = text.get("content") if isinstance(text, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise MappingValidationError(f"属性“{name}”必须包含非空文本")
    return content.strip()


def _parse_exercise(properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    exercise = _required_property(properties, "运动类型", "select")
    select = exercise.get("select")
    select_id = select.get("id") if isinstance(select, dict) else None
    if not isinstance(select_id, str) or not select_id.strip():
        raise MappingValidationError("属性“运动类型”必须包含 select.id")

    duration_property = _required_property(properties, "时长", "number")
    duration = duration_property.get("number")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise MappingValidationError("属性“时长”必须是非负数字")

    occurred_property = _required_property(properties, "记录时间", "date")
    occurred_date = occurred_property.get("date")
    occurred_value = occurred_date.get("start") if isinstance(occurred_date, dict) else None
    if not isinstance(occurred_value, str):
        raise MappingValidationError("属性“记录时间”必须包含 date.start")
    try:
        occurred_at = datetime.fromisoformat(occurred_value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MappingValidationError("属性“记录时间”不是 ISO 8601 时间") from error
    if occurred_at.tzinfo is None:
        raise MappingValidationError("属性“记录时间”必须带时区")

    day_property = _required_property(properties, "日期", "date")
    day_value = day_property.get("date")
    day_start = day_value.get("start") if isinstance(day_value, dict) else None
    if not isinstance(day_start, str):
        raise MappingValidationError("属性“日期”必须包含 date.start")
    try:
        occurred_on = date.fromisoformat(day_start)
    except ValueError as error:
        raise MappingValidationError("属性“日期”不是 YYYY-MM-DD") from error

    month = _required_property(properties, "月份", "title")
    title = month.get("title")
    if not isinstance(title, list) or not title or not isinstance(title[0], dict):
        raise MappingValidationError("属性“月份”必须包含 title 文本")
    month_str = _text_content(title[0], "月份")

    city: str | None = None
    city_property = properties.get("城市")
    if city_property is not None:
        if not isinstance(city_property, dict) or city_property.get("type") != "rich_text":
            raise MappingValidationError("属性“城市”必须是 rich_text 类型")
        rich_text = city_property.get("rich_text")
        if not isinstance(rich_text, list):
            raise MappingValidationError("属性“城市”的 rich_text 必须是数组")
        if rich_text:
            if not isinstance(rich_text[0], dict):
                raise MappingValidationError("属性“城市”包含无效文本")
            city = _text_content(rich_text[0], "城市")

    return {
        "sport_type_option_id": select_id.strip(),
        "duration": float(duration),
        "occurred_at": occurred_at,
        "occurred_on": occurred_on,
        "month_str": month_str,
        "city": city,
    }


def parse_mapping(mapper_key: str, properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """按 mapper key 解析业务数据；未知 key 视为服务端配置错误。"""
    if mapper_key == MAPPER_EXERCISE_NOTION_V1:
        return _parse_exercise(properties)
    raise RuntimeError(f"不支持的 Notion 映射器：{mapper_key}")
