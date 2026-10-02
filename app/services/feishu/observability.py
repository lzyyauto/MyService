"""按时间及容量约束的模块文件日志，不清理 Docker 管理的日志。"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from app.services.feishu.config import Observability
from app.services.feishu.files import CHINA, file_lock


class LimitedLogHandler(logging.Handler):
    """每个运行角色由单写入端维护；多个角色使用独立目录。"""

    def __init__(self, directory: Path, options: Observability) -> None:
        super().__init__()
        self.directory, self.options = directory, options
        directory.mkdir(parents=True, exist_ok=True)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        self.last_errors: dict[str, tuple[float, int]] = {}
        self.maintain()

    def maintain(self) -> None:
        with file_lock(self.directory / "journal"):
            self._maintain_unlocked()

    def _maintain_unlocked(self) -> None:
        cutoff = time.time() - self.options.retention_days * 86400
        files = sorted(self.directory.glob("feishu-*.log"), key=lambda path: path.stat().st_mtime)
        for path in files[:]:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                files.remove(path)
        total = sum(path.stat().st_size for path in files)
        while files and total > self.options.max_total_mb * 1024 * 1024:
            path = files.pop(0)
            total -= path.stat().st_size
            path.unlink()

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith(("app.services.feishu", "app.workers.feishu", "app.services.inspiration")):
            return
        with file_lock(self.directory / "journal"):
            self._emit_unlocked(record)

    def _emit_unlocked(self, record: logging.LogRecord) -> None:
        now = time.time()
        if record.levelno >= logging.WARNING:
            args = record.args if isinstance(record.args, tuple) else ()
            prefix = str(record.msg).split("error", 1)[0]
            error_index = prefix.count("%s")
            category = str(args[error_index]) if "error" in str(record.msg) and len(args) > error_index else ""
            key = f"{record.name}:{record.msg}:{category}"
            if len(self.last_errors) > 1000:
                self.last_errors.clear()
            previous, suppressed = self.last_errors.get(key, (0, 0))
            if now - previous < 60:
                self.last_errors[key] = (previous, suppressed + 1)
                return
            self.last_errors[key] = (now, 0)
            suffix = f" suppressed={suppressed}" if suppressed else ""
        else:
            suffix = ""
        # 不展开异常 traceback，防止 SDK／HTTP 异常携带载荷或凭证。
        clean = logging.makeLogRecord({**record.__dict__, "exc_info": None, "exc_text": None})
        line = (self.format(clean)[:8192] + suffix + "\n").encode("utf-8")
        date = datetime.now(CHINA).strftime("%Y-%m-%d")
        paths = sorted(self.directory.glob(f"feishu-{date}-*.log"))
        index = int(paths[-1].stem.rsplit("-", 1)[1]) if paths else 0
        path = self.directory / f"feishu-{date}-{index:06d}.log"
        if path.exists() and path.stat().st_size + len(line) > self.options.max_file_mb * 1024 * 1024:
            path = self.directory / f"feishu-{date}-{index + 1:06d}.log"
        with path.open("ab") as handle:
            handle.write(line)
        if self.options.console:
            sys.stderr.write(line.decode("utf-8"))
        self._maintain_unlocked()


def configure_logs(directory: Path, options: Observability) -> LimitedLogHandler:
    handler = LimitedLogHandler(directory, options)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(options.level)
    for name in ("lark_oapi", "urllib3", "requests", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return handler
