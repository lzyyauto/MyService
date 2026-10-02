"""飞书灵感采集 worker。"""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    # 本地直接启动兼容入口时，也识别 .env 中的新配置路径。
    load_dotenv(Path.cwd() / ".env", override=False)
    if os.environ.get("FEISHU_CONFIG_PATH"):
        from app.feishu_cli import main as cli_main
        raise SystemExit(cli_main(["--config", os.environ["FEISHU_CONFIG_PATH"], "collect"]))
    # 老配置保留单文件入口；启用新配置才使用来源目录、持久化任务和多应用接入。
    from app.core.config import settings
    from app.services.inspiration import FeishuInspirationCollector
    from app.services.feishu.config import Observability
    from app.services.feishu.observability import configure_logs

    handler = configure_logs(Path(settings.INSPIRATION_DOC_PATH).resolve().parent / "logs" / "feishu" / "collector", Observability())
    stop = threading.Event()
    def maintain_logs() -> None:
        while not stop.wait(3600):
            handler.maintain()
    maintenance = threading.Thread(target=maintain_logs, daemon=True)
    maintenance.start()
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
    try:
        collector.run()
    finally:
        stop.set()


if __name__ == "__main__":
    main()
