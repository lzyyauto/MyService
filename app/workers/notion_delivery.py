"""持久化 Notion 投递队列的独立 worker。"""

import asyncio
import logging
import time

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.notion_ingest import NotionDelivery

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def _now() -> int:
    return int(time.time())


def _claim_delivery(db: Session) -> NotionDelivery | None:
    now = _now()
    delivery = (
        db.query(NotionDelivery)
        .filter(
            or_(
                and_(
                    NotionDelivery.status == NotionDelivery.STATUS_PENDING,
                    NotionDelivery.next_attempt_at <= now,
                ),
                and_(
                    NotionDelivery.status == NotionDelivery.STATUS_PROCESSING,
                    NotionDelivery.locked_until < now,
                ),
            )
        )
        .order_by(NotionDelivery.next_attempt_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if delivery is None:
        return None
    delivery.status = NotionDelivery.STATUS_PROCESSING
    delivery.locked_until = now + settings.NOTION_DELIVERY_LEASE_SECONDS
    db.commit()
    return delivery


async def deliver_one() -> bool:
    """投递一项任务；返回是否实际领取了任务。"""
    if not settings.NOTION_TOKEN:
        return False

    db = SessionLocal()
    try:
        delivery = _claim_delivery(db)
        if delivery is None:
            return False

        from app.services.bark import BarkService
        from app.services.notion import NotionService

        error_text: str | None = None
        page_id: str | None = None
        try:
            page_id = await NotionService(settings.NOTION_TOKEN).create_page_from_payload(
                delivery.notion_payload
            )
            if not page_id:
                error_text = "Notion 未返回页面 ID"
        except Exception as error:  # 客户端异常同样计入一次明确的投递失败。
            error_text = str(error)

        delivery = db.get(NotionDelivery, delivery.id)
        assert delivery is not None
        delivery.attempt_count += 1
        delivery.locked_until = None
        if page_id:
            delivery.status = NotionDelivery.STATUS_SUCCEEDED
            delivery.notion_page_id = page_id
            delivery.last_error = None
            db.commit()
            return True

        delivery.last_error = (error_text or "未知 Notion 投递错误")[:1000]
        if delivery.attempt_count >= MAX_ATTEMPTS:
            delivery.status = NotionDelivery.STATUS_FAILED
            db.commit()
            logger.error("Notion 投递最终失败：delivery_id=%s", delivery.id)
            if settings.BARK_DEFAULT_DEVICE_KEY:
                await BarkService(
                    base_url=settings.BARK_BASE_URL,
                    default_device_key=settings.BARK_DEFAULT_DEVICE_KEY,
                ).send_notification(
                    title="Notion 同步失败",
                    content=f"投递任务 {delivery.id} 重试 {MAX_ATTEMPTS} 次后失败",
                    group="notion_deliveries",
                )
            return True

        delivery.status = NotionDelivery.STATUS_PENDING
        delivery.next_attempt_at = _now() + settings.NOTION_DELIVERY_RETRY_DELAY_SECONDS
        db.commit()
        return True
    finally:
        db.close()


async def run_worker() -> None:
    """持续消费队列；没有任务时按配置间隔轮询。"""
    while True:
        claimed = await deliver_one()
        if not claimed:
            await asyncio.sleep(settings.NOTION_DELIVERY_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_worker())
