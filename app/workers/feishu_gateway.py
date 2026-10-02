"""一个采集运行角色管理多个应用连接；子进程日志送往单一写入端。"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import threading
import time
from logging.handlers import QueueHandler, QueueListener

import lark_oapi as lark

from app.services.feishu.collection import CollectionService
from app.services.feishu.config import ConfigManager
from app.services.feishu.events import parse_event
from app.services.feishu.files import file_lock
from app.services.feishu.observability import configure_logs
from app.services.feishu.store import Store, database_url
from app.services.feishu.transport import FeishuTransport

logger = logging.getLogger(__name__)


def _connection(config_path: str, alias: str, logs) -> None:
    root = logging.getLogger()
    root.handlers = [QueueHandler(logs)]
    root.setLevel(logging.INFO)
    configs = ConfigManager(config_path)
    snapshot = configs.refresh()
    root.setLevel(snapshot.config.observability.level)
    app = snapshot.app(alias)
    transport = FeishuTransport(app)
    app_id, app_secret = transport.credentials()
    store = Store(database_url(snapshot))
    collector = CollectionService(configs, store)
    bot_id: str | None = None
    stop = threading.Event()
    if any(route.app == alias and route.require_at for route in snapshot.config.routes):
        # 首条消息到达前确认机器人身份；失败时严格过滤，后台继续恢复查询。
        try:
            bot_id = transport.bot_open_id()
        except Exception as error:
            logger.warning("event=feishu.bot_identity_failed app=%s error_type=%s", alias, type(error).__name__)

    def consume() -> None:
        nonlocal bot_id
        while not stop.wait(snapshot.config.runtime.poll_seconds):
            try:
                current = configs.refresh()
                root.setLevel(current.config.observability.level)
                if any(route.app == alias and route.require_at for route in current.config.routes) and bot_id is None:
                    bot_id = transport.bot_open_id()
                collector.flush(alias)
            except Exception as error:
                logger.error("event=feishu.consumer_failed app=%s error_type=%s", alias, type(error).__name__)

    def receive(data) -> None:
        try:
            message = parse_event(data, alias, app_id, bot_id)
        except (AttributeError, TypeError, ValueError) as error:
            logger.warning("event=feishu.invalid_event app=%s error_type=%s", alias, type(error).__name__)
            return
        # 持久化失败必须向 SDK 传播，不能 ACK 一个只在内存里接受的事件。
        collector.receive(message)

    consumer = threading.Thread(target=consume, name=f"writer-{alias}", daemon=True)
    consumer.start()
    event_handler = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(receive).build()
    client = lark.ws.Client(app_id, app_secret, event_handler=event_handler, domain=app.base_url, log_level=lark.LogLevel.ERROR)
    logger.info("event=feishu.connected_start app=%s app_id=%s", alias, app_id)
    try:
        client.start()
    finally:
        stop.set()
        consumer.join(timeout=15)
        store.close()


def _signature(app) -> tuple:
    return (app.app_id_env, app.app_secret_env, app.base_url, os.environ.get(app.app_id_env), os.environ.get(app.app_secret_env))


def run_gateway(config_path: str) -> None:
    configs = ConfigManager(config_path)
    snapshot = configs.refresh()
    with file_lock(snapshot.path(snapshot.config.observability.log_dir) / "collector" / "role", blocking=False):
        _run_gateway(config_path)


def _run_gateway(config_path: str) -> None:
    configs = ConfigManager(config_path)
    snapshot = configs.refresh()
    handler = configure_logs(snapshot.path(snapshot.config.observability.log_dir) / "collector", snapshot.config.observability)
    context = mp.get_context("spawn")
    log_queue = context.Queue(maxsize=1000)
    listener = QueueListener(log_queue, handler)
    listener.start()
    children: dict[str, tuple[mp.Process, tuple]] = {}
    restart_after: dict[str, float] = {}
    last_maintenance = 0.0
    store = Store(database_url(snapshot))
    try:
        while True:
            snapshot = configs.refresh()
            logging.getLogger().setLevel(snapshot.config.observability.level)
            handler.options = snapshot.config.observability
            wanted = {app.id: app for app in snapshot.config.apps if app.enabled}
            for alias, (process, signature) in list(children.items()):
                app = wanted.get(alias)
                current = _signature(app) if app else None
                if current != signature or not process.is_alive():
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=15)
                    if process.is_alive():
                        process.kill()
                        process.join()
                    del children[alias]
                    restart_after[alias] = time.monotonic() + 5
                    logger.info("event=feishu.connection_restart app=%s", alias)
            for alias, app in wanted.items():
                if alias not in children and time.monotonic() >= restart_after.get(alias, 0):
                    FeishuTransport(app).credentials()
                    process = context.Process(target=_connection, args=(config_path, alias, log_queue), name=f"feishu-{alias}")
                    process.start()
                    children[alias] = (process, _signature(app))
            if time.monotonic() - last_maintenance >= 3600:
                handler.maintain()
                store.maintain_sources(snapshot.config.observability.source_retention_days, snapshot.config.observability.max_sources)
                last_maintenance = time.monotonic()
            time.sleep(snapshot.config.runtime.poll_seconds)
    finally:
        for process, _ in children.values():
            process.terminate()
            process.join(timeout=15)
            if process.is_alive():
                process.kill()
                process.join()
        listener.stop()
        log_queue.close()
        store.close()
