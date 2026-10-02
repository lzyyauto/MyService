"""停采集后，将兼容 SQLite 的采集状态导入 PostgreSQL，不覆盖已有记录。"""

from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL

from app.models.feishu import FEISHU_TABLES
from app.services.feishu.store import Store


def import_sqlite(source: Path, target: Store) -> dict:
    source = source.expanduser().resolve(strict=True)
    if target.engine.dialect.name != "postgresql":
        raise ValueError("旧状态只能导入已迁移的 PostgreSQL")
    reader = create_engine(URL.create("sqlite", database=f"file:{source}", query={"mode": "ro", "uri": "true"}))
    counts = {}
    try:
        with reader.connect() as old, target.engine.begin() as new:
            old.execute(text("BEGIN"))
            # 未完成项包含原绝对路径和文件身份，不能盲目带往另一运行环境。
            outstanding = old.execute(text("""SELECT COUNT(*) FROM feishu_messages
                WHERE status IN ('pending', 'failed')
                   OR (status = 'written' AND reaction_status IN ('pending', 'failed'))""")).scalar_one()
            if outstanding:
                raise ValueError("旧状态仍有待处理或失败项，请先在原采集环境处理完毕")
            for table in FEISHU_TABLES:
                inserted = skipped = 0
                for row in old.execute(select(table)).mappings():
                    if new.execute(select(table.c.id).where(table.c.id == row["id"])).first():
                        skipped += 1
                    else:
                        new.execute(table.insert().values(dict(row)))
                        inserted += 1
                counts[table.name] = {"inserted": inserted, "skipped": skipped}
    finally:
        reader.dispose()
    return {"imported": True, "tables": counts, "source_modified": False}
