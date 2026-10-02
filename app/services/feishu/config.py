"""校验 TOML 并在变更时原子替换最后有效配置。"""

from __future__ import annotations

import hashlib
import logging
import string
import threading
import time
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
TEMPLATE_FIELDS = {"app_id", "chat_id", "pipeline_id"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Runtime(StrictModel):
    root_dir: str = ".."
    database_url_env: str = "FEISHU_STATE_DATABASE_URL"
    state_backend: Literal["postgresql", "sqlite"] = "postgresql"
    state_path: str = "data/feishu/state.sqlite3"
    poll_seconds: float = Field(default=1, gt=0, le=60)
    retry_seconds: int = Field(default=30, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class Discovery(StrictModel):
    enabled: bool = False
    duration_seconds: int = Field(default=600, ge=1, le=3600)


class Observability(StrictModel):
    level: str = "INFO"
    console: bool = False
    summary_interval_seconds: int = Field(default=300, ge=1)
    log_dir: str = "data/logs/feishu"
    retention_days: int = Field(default=7, ge=1)
    max_file_mb: int = Field(default=10, ge=1)
    max_total_mb: int = Field(default=100, ge=1)
    source_retention_days: int = Field(default=90, ge=1)
    max_sources: int = Field(default=10_000, ge=1)
    discovery: Discovery = Field(default_factory=Discovery)

    @model_validator(mode="after")
    def validate_budget(self) -> Observability:
        if self.max_total_mb < self.max_file_mb:
            raise ValueError("日志总量上限不能小于单文件上限")
        if self.level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError("无效日志级别")
        return self


class App(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    app_id_env: str
    app_secret_env: str
    default_pipeline: str
    base_url: str = "https://open.feishu.cn"
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("飞书域名必须是不含鉴权、查询参数和 fragment 的 HTTP(S) 前缀")
        return value.rstrip("/")


class Route(StrictModel):
    id: str
    app: str
    chat_id: str | None = None
    chat_type: str | None = Field(default=None, pattern=r"^(p2p|group)$")
    allowed_sender_ids: list[str] = Field(default_factory=list)
    require_at: bool = False
    pipeline: str


class Pipeline(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    handler: str = "markdown_collect"
    enabled: bool = True
    input_path: str


class FeishuConfig(StrictModel):
    version: int = 1
    runtime: Runtime = Field(default_factory=Runtime)
    observability: Observability = Field(default_factory=Observability)
    apps: list[App]
    routes: list[Route] = Field(default_factory=list)
    pipelines: list[Pipeline]

    @model_validator(mode="after")
    def validate_links(self) -> FeishuConfig:
        if self.version != 1:
            raise ValueError("只支持配置 version=1")
        apps = {item.id for item in self.apps}
        pipelines = {item.id for item in self.pipelines}
        if len(apps) != len(self.apps) or len(pipelines) != len(self.pipelines):
            raise ValueError("应用／流程 ID 必须唯一")
        seen_routes: set[tuple[str, str | None, str | None]] = set()
        if len({r.id for r in self.routes}) != len(self.routes):
            raise ValueError("路由 ID 必须唯一")
        for app in self.apps:
            if app.default_pipeline not in pipelines:
                raise ValueError("默认流程不存在")
        for route in self.routes:
            if route.app not in apps or route.pipeline not in pipelines:
                raise ValueError("路由引用不存在")
            route_key = (route.app, route.chat_id, route.chat_type)
            if route_key in seen_routes:
                raise ValueError("相同优先级路由冲突")
            seen_routes.add(route_key)
        for pipeline in self.pipelines:
            if pipeline.handler != "markdown_collect":
                raise ValueError("未注册的采集处理器")
            if not pipeline.input_path.strip():
                raise ValueError("文档路径不能为空")
            for _, field, spec, conversion in string.Formatter().parse(pipeline.input_path):
                if field is not None and (field not in TEMPLATE_FIELDS or spec or conversion):
                    raise ValueError("文件路径只支持 app_id／chat_id／pipeline_id")
        return self


class ConfigSnapshot:
    """不可变的采集配置与文件路径解析。"""

    def __init__(self, config: FeishuConfig, root: Path, version: str) -> None:
        self.config, self.root, self.version = config, root, version

    def app(self, alias: str) -> App:
        return next(item for item in self.config.apps if item.id == alias)

    def pipeline(self, name: str) -> Pipeline:
        return next(item for item in self.config.pipelines if item.id == name)

    def path(self, template: str, **values: str) -> Path:
        safe = {key: sanitize(str(value)) for key, value in values.items()}
        path = Path(template.format(**safe)).expanduser()
        return (path if path.is_absolute() else self.root / path).resolve()


def sanitize(value: str) -> str:
    if not value or any(char not in string.ascii_letters + string.digits + "_-" for char in value):
        raise ValueError("路径变量只能使用字母、数字、下划线和连字符")
    return value


class ConfigManager:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.current: ConfigSnapshot | None = None
        self._signature: Any = None
        self._lock = threading.RLock()
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> ConfigSnapshot:
        with self._lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
                if not force and signature == self._signature:
                    assert self.current is not None
                    return self.current
                self._signature = signature
                raw = self.path.read_bytes()
                config = FeishuConfig.model_validate(tomllib.loads(raw.decode("utf-8")))
                root = (self.path.parent / config.runtime.root_dir).resolve()
                snapshot = ConfigSnapshot(config, root, hashlib.sha256(raw).hexdigest()[:16])
                paths: set[Path] = set()
                for pipeline in config.pipelines:
                    values = dict(app_id="cli_example", chat_id="oc_example", pipeline_id=pipeline.id)
                    path = snapshot.path(pipeline.input_path, **values)
                    if path in paths:
                        raise ValueError("不同收集目标不能共享同一个文档，请使用同一个目标 ID")
                    paths.add(path)
                    if path.is_relative_to(snapshot.path(config.observability.log_dir)):
                        raise ValueError("业务文件不能放在模块日志清理目录中")
                    if path == snapshot.path(config.runtime.state_path):
                        raise ValueError("文档与内部状态库路径不能相同")
                if self.current:
                    if self.current.config.runtime != config.runtime:
                        raise ValueError("运行时状态库／根目录／轮询配置变化需要重启进程")
                    if self.current.config.observability.log_dir != config.observability.log_dir:
                        raise ValueError("日志目录变化需要重启进程，避免角色锁与日志清理目录失去一致性")
                changed = self.current is None or self.current.version != snapshot.version
                self.current = snapshot
                if changed:
                    logger.info("event=config.loaded version=%s", snapshot.version)
                return snapshot
            except (OSError, ValueError, StopIteration) as error:
                if self.current is None:
                    raise ValueError("配置校验失败，请执行 validate 查看字段错误") from error
                logger.warning("event=config.rejected error_type=%s using_version=%s", type(error).__name__, self.current.version)
                return self.current
