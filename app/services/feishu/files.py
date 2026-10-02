"""文件锁、可核对的追加格式与删除／重建识别。"""

from __future__ import annotations

import fcntl
import os
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CHINA = ZoneInfo("Asia/Shanghai")


@contextmanager
def file_lock(path: Path, blocking: bool = True):
    """Linux／macOS 多进程锁；锁文件用于保护采集追加，不属于业务文档。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(f".{path.name}.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def identity(path: Path) -> str | None:
    try:
        stat = path.stat()
        return f"{stat.st_dev}:{stat.st_ino}"
    except FileNotFoundError:
        return None


def current_batch(path: Path, file_identity: str | None, batch: str) -> bool:
    """inode 与批次标识同时确认，防止删除／重建时 inode 被操作系统复用。"""
    if identity(path) != file_identity or file_identity is None:
        return False
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline(200)
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 256))
            tail = handle.read().decode("utf-8", errors="ignore")
        markers = re.findall(r"<!-- myservice-batch:([A-Za-z0-9_-]+) -->", tail)
        if markers:
            return markers[-1] == batch
        # 首次接管历史文件尚没有标识，追加时将补齐。
        return not first.startswith("<!-- myservice-batch:") or first.strip() == f"<!-- myservice-batch:{batch} -->"
    except FileNotFoundError:
        return False


def append_record(path: Path, record_id: str, text: str, timestamp_ms: int, sender: str, batch: str, chat_id: str | None = None) -> None:
    """完整结束标识确认追加完成；崩溃留下的半条记录重写。调用方必须持有文件锁。"""
    begin, end = f"<!-- myservice-message:{record_id} -->", f"<!-- myservice-end:{record_id} -->"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if end in existing:
        return
    if begin in existing:
        existing = existing[:existing.index(begin)]
        # 原地截断，避免恢复半条记录时换 inode，被误判为用户更换了文档。
        with path.open("r+b") as handle:
            handle.truncate(len(existing.encode("utf-8")))
            handle.flush()
            os.fsync(handle.fileno())
    created = datetime.fromtimestamp(timestamp_ms / 1000, CHINA).isoformat(sep=" ", timespec="seconds")
    source = f"{sender}; chat={chat_id}" if chat_id else sender
    content = f"{begin}\n- [{created}] ({source}) {text}\n<!-- myservice-batch:{batch} -->\n{end}\n"
    with path.open("a", encoding="utf-8") as handle:
        if not existing:
            handle.write(f"<!-- myservice-batch:{batch} -->\n")
        elif not existing.endswith("\n"):
            handle.write("\n")
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
