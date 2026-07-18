"""飞书灵感采集 worker。"""

import logging

from app.core.config import settings
from app.main import setup_logging
from app.services.inspiration import FeishuInspirationCollector


def main() -> None:
    setup_logging()
    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        raise SystemExit(
            "请先配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET，再启动飞书灵感采集 worker"
        )

    collector = FeishuInspirationCollector(
        app_id=settings.FEISHU_APP_ID,
        app_secret=settings.FEISHU_APP_SECRET,
        base_url=settings.FEISHU_BASE_URL,
        target_path=settings.INSPIRATION_DOC_PATH,
    )
    collector.run()


if __name__ == "__main__":
    main()
