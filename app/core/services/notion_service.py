from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from notion_client import Client

from app.models.rest_record import RestRecord
from app.schemas.rest_record import RestRecord as RestRecordSchema


class NotionService:

    def __init__(self, token: str):
        """
        初始化 Notion 服务
        
        Args:
            token: Notion API token
        """
        self.client = Client(auth=token)

    async def create_page(
            self,
            database_id: str,
            properties: Dict[str, Any],
            title_property: Optional[str] = None,
            title_content: Optional[str] = None) -> Optional[str]:
        """
        创建 Notion 页面
        
        Args:
            database_id: 数据库 ID
            properties: 属性数据，格式为 {属性名: {类型: 值}}
            title_property: 标题属性名，如果不提供则使用第一个属性
            title_content: 标题内容，如果不提供则使用属性名
            
        Returns:
            Notion 页面 ID，如果失败返回 None
        """
        try:
            # 构建页面数据
            page_data = {
                "parent": {
                    "database_id": database_id
                },
                "properties": {}
            }

            # 处理属性
            for prop_name, prop_data in properties.items():
                if prop_name == title_property:
                    # 处理标题属性
                    page_data["properties"][prop_name] = {
                        "title": [{
                            "text": {
                                "content": title_content or prop_name
                            }
                        }]
                    }
                else:
                    # 处理其他属性
                    page_data["properties"][prop_name] = self._format_property(
                        prop_data)

            # 如果没有指定标题属性，使用第一个属性作为标题
            if not title_property and properties:
                first_prop = next(iter(properties.items()))
                page_data["properties"][first_prop[0]] = {
                    "title": [{
                        "text": {
                            "content": title_content or first_prop[0]
                        }
                    }]
                }

            response = self.client.pages.create(**page_data)
            return response.get('id')
        except Exception as e:
            print(f"Notion 数据同步失败: {str(e)}")
            return None

    def _format_property(self, prop_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化属性数据
        
        Args:
            prop_data: 属性数据，格式为 {类型: 值}
            
        Returns:
            格式化后的属性数据
        """
        prop_type = prop_data.get("type")
        value = prop_data.get("value")

        if prop_type == "title":
            return {"title": [{"text": {"content": str(value)}}]}
        elif prop_type == "text":
            return {"rich_text": [{"text": {"content": str(value)}}]}
        elif prop_type == "number":
            return {"number": float(value) if value is not None else None}
        elif prop_type == "date":
            if isinstance(value, (int, float)):
                # 如果是时间戳，转换为 ISO 格式
                value = datetime.fromtimestamp(value).isoformat()
            return {"date": {"start": value}}
        elif prop_type == "select":
            return {"select": {"name": str(value)}}
        else:
            raise ValueError(f"不支持的属性类型: {prop_type}")

    async def add_rest_record(
        self, database_id: str, record: Union[Dict[str, Any], RestRecord,
                                              RestRecordSchema]
    ) -> Optional[str]:
        """
        添加休息记录到 Notion 数据库
        
        Args:
            database_id: 数据库 ID
            record: 休息记录数据，可以是字典、RestRecord 模型或 RestRecordSchema
            
        Returns:
            Notion 页面 ID，如果失败返回 None
        """
        # 统一转换为字典格式
        if hasattr(record, "model_dump"):  # Pydantic v2
            record_dict = record.model_dump(by_alias=False,
                                            exclude_unset=False)
        elif hasattr(record, "__dict__"):  # SQLAlchemy ORM
            record_dict = {
                k: v
                for k, v in record.__dict__.items() if not k.startswith("_")
            }
        else:
            record_dict = record

        # 如果 record_dict 里没有 rest_time，则直接使用当前时间戳
        if "rest_time" not in record_dict:
            record_dict["rest_time"] = int(datetime.now().timestamp())

        rest_time = datetime.fromtimestamp(
            record_dict["rest_time"]).isoformat()
        rest_date = datetime.fromtimestamp(
            record_dict["rest_time"]).strftime("%Y-%m-%d")

        # 构建属性数据（去掉 Notion 数据库中不存在的字段，比如"类型"）
        properties = {
            "月份": {
                "type":
                "title",
                "value":
                record_dict.get("month_str") or datetime.fromtimestamp(
                    record_dict["rest_time"]).strftime("%m月")
            },
            "日期": {
                "type": "date",
                "value": rest_date
            },
            "城市": {
                "type": "text",
                "value": record_dict.get("city") or ""
            },
            "经度": {
                "type": "number",
                "value": record_dict.get("longitude")
            },
            "纬度": {
                "type": "number",
                "value": record_dict.get("latitude")
            },
            "记录时间": {
                "type": "date",
                "value": rest_time
            },
            "WiFi": {
                "type": "text",
                "value": record_dict.get("wifi_name") or ""
            }
        }

        return await self.create_page(
            database_id=database_id,
            properties=properties,
            title_property=record_dict.get("month_str"))

    async def add_gtd_task(self, database_id: str,
                           task: Dict[str, Any]) -> Optional[str]:
        """
        添加 GTD 任务到 Notion 数据库
        
        Args:
            database_id: 数据库 ID
            task: 任务数据
            
        Returns:
            Notion 页面 ID，如果失败返回 None
        """
        # 转换时间戳为 ISO 格式
        start_time = datetime.fromtimestamp(task['start_time']).isoformat()
        end_time = datetime.fromtimestamp(task['end_time']).isoformat()

        # 构建属性数据
        properties = {
            "名称": {
                "type": "title",
                "value": task['name']
            },
            "状态": {
                "type": "select",
                "value": {
                    0: "待办",
                    1: "进行中",
                    2: "已完成",
                    3: "已取消"
                }[task['status']]
            },
            "优先级": {
                "type": "number",
                "value": task['priority']
            },
            "分类": {
                "type": "select",
                "value": task['category']
            },
            "开始时间": {
                "type": "date",
                "value": start_time
            },
            "结束时间": {
                "type": "date",
                "value": end_time
            }
        }

        return await self.create_page(
            database_id=database_id,
            properties=properties,
            title_property=record_dict.get("month_str"))
