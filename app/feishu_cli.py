"""飞书文本采集与来源查询；不提供 AI、定时整理或结果投递入口。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.exc import DBAPIError

from app.services.feishu.collection import CollectionService
from app.services.feishu.config import ConfigManager
from app.services.feishu.events import Message
from app.services.feishu.observability import configure_logs
from app.services.feishu.store import Store, database_url
from app.services.feishu.transport import FeishuError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="飞书长连接、Markdown 收集与来源查询")
    root.add_argument("--config", help="配置路径；默认使用 .env 的 FEISHU_CONFIG_PATH 或 config/feishu.toml")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="仅校验采集配置，不访问状态库或网络")
    sub.add_parser("init-local", help="兼容入口；采集 SQLite 已在启动时自动初始化")
    sub.add_parser("collect", help="启动应用长连接、文档写入与基本回执")
    sources = sub.add_parser("sources", help="查询实际观察到的来源 ID")
    sources.add_argument("--app")
    sources.add_argument("--kind", choices=["p2p", "group"])
    sources.add_argument("--limit", type=int, default=100)
    sources.add_argument("--offset", type=int, default=0)
    discover = sub.add_parser("discover", help="开启或关闭自动到期的详细来源发现")
    discover.add_argument("--app", required=True)
    discover.add_argument("--seconds", type=int, default=600, help="0 表示关闭，最大 3600")
    sub.add_parser("status", help="查看文档目标和写入／回执状态，不输出正文")
    simulate = sub.add_parser("simulate", help="测试文本落盘，不连接飞书或发送回执")
    simulate.add_argument("--app", required=True)
    simulate.add_argument("--chat-id", default="oc_local")
    simulate.add_argument("--kind", choices=["p2p", "group"], default="p2p")
    simulate.add_argument("--sender-id", default="ou_local")
    simulate.add_argument("--text", required=True)
    logs = sub.add_parser("logs", help="读取正式文件日志，无需 docker logs")
    logs.add_argument("--role", choices=["collector", "cli"], default="collector")
    logs.add_argument("--lines", type=int, default=100)
    return root


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if threading.current_thread() is threading.main_thread():
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
    try:
        if args.config is None:
            load_dotenv(Path.cwd() / ".env", override=False)
            args.config = os.environ.get("FEISHU_CONFIG_PATH") or "config/feishu.toml"
        configs = ConfigManager(args.config)
        snapshot = configs.refresh()
        load_dotenv(snapshot.root / ".env", override=False)
        if args.command == "validate":
            emit({"valid": True, "config_version": snapshot.version, "apps": [a.id for a in snapshot.config.apps],
                  "pipelines": [p.id for p in snapshot.config.pipelines], "root": str(snapshot.root)})
            return 0
        if args.command == "logs":
            if not 1 <= args.lines <= 10000:
                raise ValueError("日志行数必须在 1 至 10000 之间")
            tail = deque(maxlen=args.lines)
            for path in sorted((snapshot.path(snapshot.config.observability.log_dir) / args.role).glob("feishu-*.log")):
                with path.open(encoding="utf-8") as handle:
                    tail.extend(handle)
            print("".join(tail), end="")
            return 0
        if args.command == "collect":
            from app.workers.feishu_gateway import run_gateway
            run_gateway(str(configs.path))
            return 0
        configure_logs(snapshot.path(snapshot.config.observability.log_dir) / "cli", snapshot.config.observability)
        store = Store(database_url(snapshot))
        try:
            if args.command == "init-local":
                emit({"initialized": True, "mode": "local_sqlite", "automatic": True})
            elif args.command == "sources":
                if not 1 <= args.limit <= 1000 or args.offset < 0:
                    raise ValueError("分页 limit 必须在 1 至 1000 之间，offset 不得为负")
                emit(store.sources(args.app, args.kind, args.limit, args.offset))
            elif args.command == "status":
                emit({**store.counts(), "streams": [{"stream_id": s.id, "pipeline": s.pipeline,
                     "input_path": s.input_path} for s in store.streams()]})
            elif args.command == "discover":
                snapshot.app(args.app)
                store.discover(args.app, args.seconds)
                emit({"app": args.app, "enabled": args.seconds > 0, "expires_at": int(time.time()) + args.seconds})
            elif args.command == "simulate":
                app = snapshot.app(args.app)
                message = Message(args.app, "cli_local", f"local_{uuid.uuid4().hex}", args.chat_id, args.kind,
                                  args.sender_id, None, int(time.time() * 1000), args.text, "text")
                collection = CollectionService(configs, store)
                accepted = collection.receive(message)
                written = collection.flush(app.id, acknowledge=False)
                emit({"accepted": accepted, "written": written, "network_requests": 0})
        finally:
            store.close()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        # 不输出 DB URL、SQL 参数、HTTP 正文或原始凭证。
        details = []
        error_code = error.code if isinstance(error, FeishuError) else None
        hint = "请检查采集配置、内部 SQLite 文件权限和 collector 日志"
        if error_code == "feishu_credentials_missing":
            hint = "app_id_env／app_secret_env 填环境变量名，实际凭证放配置根目录 .env 或进程环境"
        if isinstance(error, DBAPIError):
            error_code = "collection_state_error"
        cause = error.__cause__
        if args.command == "validate" and cause and hasattr(cause, "errors"):
            details = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]} for item in cause.errors()]
        emit({"ok": False, "error_type": type(error).__name__, "error_code": error_code,
              "fields": details, "hint": hint})
        return 1


if __name__ == "__main__":
    sys.exit(main())
