"""Deployment diagnostics, backups and operator recovery helpers."""

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from sqlalchemy import text

from . import db
from .config import BASE_DIR
from .models import User


BACKUP_FORMAT_VERSION = 1


def _utc_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _database_kind(app):
    return db.engine.url.get_backend_name()


def _sqlite_path(app):
    database = db.engine.url.database
    if not database or database == ":memory:":
        raise ValueError("内存数据库无法备份或恢复")
    return Path(database).expanduser().resolve()


def _postgres_conninfo(app):
    value = str(app.config["SQLALCHEMY_DATABASE_URI"])
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _assert_pg_tool(name):
    if shutil.which(name) is None:
        raise RuntimeError(
            f"未找到 {name}。PostgreSQL 备份/恢复需要安装 PostgreSQL 客户端工具。"
        )


def _backup_database(app, target):
    kind = _database_kind(app)
    if kind == "sqlite":
        source_path = _sqlite_path(app)
        if not source_path.exists():
            raise FileNotFoundError(f"数据库文件不存在：{source_path}")
        with closing(
            sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True)
        ) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
            result = destination.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("SQLite 备份完整性检查失败")
        return {"kind": "sqlite", "file": "database/doc_collab.sqlite"}

    if kind == "postgresql":
        _assert_pg_tool("pg_dump")
        try:
            subprocess.run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--file",
                    str(target),
                    _postgres_conninfo(app),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()[-1500:]
            raise RuntimeError(f"pg_dump 失败：{detail}") from exc
        return {"kind": "postgresql", "file": "database/doc_collab.dump"}

    raise ValueError(f"不支持的数据库类型：{kind}")


def _backup_media(app, archive):
    backend = str(app.config.get("STORAGE_BACKEND") or "local").lower()
    if backend != "local":
        return {
            "backend": backend,
            "included": False,
            "warning": "对象存储文件未打包；请为 COS 开启版本控制并单独配置备份。",
        }

    root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    count = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith(".readiness-"):
            continue
        relative = path.relative_to(root).as_posix()
        archive.write(path, f"media/{relative}")
        count += 1
    return {"backend": "local", "included": True, "file_count": count}


def create_backup(app, output=None, overwrite=False):
    """Create an atomically written ZIP with a consistent DB and local media."""
    backup_folder = Path(app.config["BACKUP_FOLDER"]).expanduser().resolve()
    if str(app.config.get("STORAGE_BACKEND") or "local").lower() == "local":
        upload_folder = Path(app.config["UPLOAD_FOLDER"]).resolve()
        if backup_folder == upload_folder or backup_folder.is_relative_to(
            upload_folder
        ):
            raise ValueError("BACKUP_FOLDER 不能位于 UPLOAD_FOLDER 内")
    backup_folder.mkdir(parents=True, exist_ok=True)
    output_path = (
        Path(output).expanduser().resolve()
        if output
        else backup_folder / f"doc-collab-{_utc_stamp()}.zip"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"备份文件已存在：{output_path}")

    with tempfile.TemporaryDirectory(prefix="doc-collab-backup-") as temp:
        temp_dir = Path(temp)
        (temp_dir / "database").mkdir()
        database_file = temp_dir / "database" / "_database"
        database = _backup_database(app, database_file)
        destination = temp_dir / database["file"]
        if database_file != destination:
            database_file.replace(destination)

        media = {"backend": "local", "included": True, "file_count": 0}
        manifest = {
            "format_version": BACKUP_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": database,
            "media": media,
            "app_environment": app.config.get("APP_ENV", "development"),
        }
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        with zipfile.ZipFile(
            partial, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            for path in (temp_dir / "database").iterdir():
                archive.write(path, arcname=f"database/{path.name}")
            media = _backup_media(app, archive)
            # The manifest must be written after media is known.
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {**manifest, "media": media},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        os.replace(partial, output_path)

    return {
        "path": str(output_path),
        "database": database,
        "media": media,
    }


def prune_backups(folder, keep):
    """Keep only the newest automatic ``doc-collab-*.zip`` backups."""
    if keep < 1:
        raise ValueError("备份保留数量至少为 1")
    backup_folder = Path(folder).expanduser().resolve()
    if not backup_folder.exists():
        return 0
    candidates = sorted(
        (
            path
            for path in backup_folder.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".zip"
            and path.name.startswith("doc-collab-")
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    removed = 0
    for path in candidates[keep:]:
        path.unlink()
        removed += 1
    return removed


def inspect_backup(path):
    archive_path = Path(path).expanduser().resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"备份文件不存在：{archive_path}")

    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        bad_members = []
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts:
                bad_members.append(name)
        if bad_members:
            raise ValueError("备份包包含不安全路径，拒绝恢复")
        if "manifest.json" not in names:
            raise ValueError("备份包缺少 manifest.json")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError("不支持的备份格式版本")
        database_file = (manifest.get("database") or {}).get("file")
        if not database_file or database_file not in names:
            raise ValueError("备份包缺少数据库文件")

    return {"path": str(archive_path), "manifest": manifest, "members": names}


def restore_backup(app, path):
    inspected = inspect_backup(path)
    manifest = inspected["manifest"]
    target_kind = _database_kind(app)
    source_kind = (manifest.get("database") or {}).get("kind")
    if source_kind != target_kind:
        raise ValueError(
            f"备份数据库类型为 {source_kind}，当前环境为 {target_kind}"
        )

    with tempfile.TemporaryDirectory(prefix="doc-collab-restore-") as temp:
        temp_dir = Path(temp)
        with zipfile.ZipFile(inspected["path"], "r") as archive:
            archive.extractall(temp_dir)

        db.session.remove()
        db.engine.dispose()
        database_source = temp_dir / manifest["database"]["file"]
        if target_kind == "sqlite":
            with closing(sqlite3.connect(database_source)) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("待恢复的 SQLite 数据库未通过完整性检查")
            database_target = _sqlite_path(app)
            for suffix in ("-wal", "-shm"):
                Path(str(database_target) + suffix).unlink(missing_ok=True)
            shutil.copyfile(database_source, database_target)
        else:
            _assert_pg_tool("pg_restore")
            try:
                subprocess.run(
                    [
                        "pg_restore",
                        "--clean",
                        "--if-exists",
                        "--no-owner",
                        "--no-privileges",
                        "--dbname",
                        _postgres_conninfo(app),
                        str(database_source),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or "").strip()[-1500:]
                raise RuntimeError(f"pg_restore 失败：{detail}") from exc

        media_manifest = manifest.get("media") or {}
        if media_manifest.get("included"):
            media_source = temp_dir / "media"
            media_target = Path(app.config["UPLOAD_FOLDER"]).resolve()
            media_target.mkdir(parents=True, exist_ok=True)
            if media_source.exists():
                shutil.copytree(
                    media_source, media_target, dirs_exist_ok=True
                )

    db.engine.dispose()
    db.session.remove()
    return inspected


def _check_result(level, name, message):
    return {"level": level, "name": name, "message": message}


def run_doctor(app):
    checks = []
    public = bool(app.config.get("PUBLIC_DEPLOYMENT")) or (
        app.config.get("APP_ENV") == "production"
    )

    secret = app.config.get("SECRET_KEY") or ""
    if public and (secret == "dev-secret-change-me" or len(secret) < 32):
        checks.append(
            _check_result(
                "error",
                "SECRET_KEY",
                "公网环境必须配置至少 32 字符的随机 SECRET_KEY",
            )
        )
    else:
        checks.append(_check_result("ok", "SECRET_KEY", "会话密钥已配置"))

    if public and not app.config.get("SESSION_COOKIE_SECURE", False):
        checks.append(
            _check_result(
                "error",
                "Session Cookie",
                "公网 HTTPS 环境必须设置 SESSION_COOKIE_SECURE=1",
            )
        )
    else:
        checks.append(_check_result("ok", "Session Cookie", "Cookie 安全属性有效"))

    if public and app.config.get("WECHAT_MOCK_ENABLED", True):
        checks.append(
            _check_result(
                "error",
                "微信演示登录",
                "公网环境必须设置 WECHAT_MOCK_ENABLED=0，避免绕过正常登录",
            )
        )
    else:
        checks.append(_check_result("ok", "微信演示登录", "未启用演示登录"))

    if public and app.config.get("SHOW_DEMO_CREDENTIALS", True):
        checks.append(
            _check_result(
                "error",
                "演示凭据展示",
                "公网环境必须设置 SHOW_DEMO_CREDENTIALS=0",
            )
        )
    else:
        checks.append(
            _check_result("ok", "演示凭据展示", "登录页不展示演示账号")
        )

    try:
        db.session.execute(text("SELECT 1 FROM users LIMIT 1"))
        checks.append(_check_result("ok", "数据库", "连接与核心表正常"))
    except Exception as exc:
        db.session.rollback()
        checks.append(
            _check_result("error", "数据库", f"连接或表结构异常：{exc}")
        )

    try:
        app.extensions["storage"].probe()
        checks.append(_check_result("ok", "文件存储", "读写探针通过"))
    except Exception as exc:
        checks.append(_check_result("error", "文件存储", f"存储不可用：{exc}"))

    try:
        admin_count = User.query.filter_by(role="admin").count()
        if admin_count:
            checks.append(
                _check_result("ok", "管理员账号", f"共有 {admin_count} 个管理员")
            )
        else:
            checks.append(
                _check_result("error", "管理员账号", "系统没有管理员，无法维护")
            )

        weak_accounts = []
        for username, password in (
            ("admin", "admin123"),
            ("teacher", "teacher123"),
            ("viewer", "viewer123"),
        ):
            user = User.query.filter_by(username=username).first()
            if user is not None and user.check_password(password):
                weak_accounts.append(username)
        if public and weak_accounts:
            checks.append(
                _check_result(
                    "error",
                    "演示弱口令",
                    "公网环境发现弱口令账号：" + ", ".join(weak_accounts),
                )
            )
        else:
            checks.append(_check_result("ok", "演示弱口令", "未发现可用弱口令"))
    except Exception as exc:
        db.session.rollback()
        checks.append(
            _check_result("error", "账号检查", f"无法检查账号：{exc}")
        )

    if db.engine.url.get_backend_name() == "sqlite":
        database_path = _sqlite_path(app)
        if (
            public
            and database_path
            == (BASE_DIR / "instance" / "doc_collab.db").resolve()
        ):
            checks.append(
                _check_result(
                    "error",
                    "数据持久化",
                    "公网环境不能使用默认 instance SQLite 路径；请挂载持久磁盘或使用 PostgreSQL",
                )
            )
        else:
            checks.append(
                _check_result("ok", "数据持久化", f"SQLite 路径：{database_path}")
            )

    default_media = (BASE_DIR / "media").resolve()
    if public and Path(app.config["UPLOAD_FOLDER"]).resolve() == default_media:
        checks.append(
            _check_result(
                "error",
                "文件持久化",
                "公网环境必须把 UPLOAD_FOLDER 指向持久磁盘或改用 COS",
            )
        )
    elif str(app.config.get("STORAGE_BACKEND")).lower() == "local":
        checks.append(_check_result("ok", "文件持久化", "上传目录已独立配置"))

    if app.config.get("COSMOS_API_KEY"):
        checks.append(_check_result("ok", "AI 服务", "模型密钥已配置"))
    else:
        checks.append(
            _check_result(
                "warning",
                "AI 服务",
                "模型未配置；文档、表格、问答和人工兜底流程仍可使用",
            )
        )

    try:
        backup_folder = Path(app.config["BACKUP_FOLDER"]).expanduser()
        backup_folder.mkdir(parents=True, exist_ok=True)
        probe = backup_folder / ".doctor-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        if (
            public
            and backup_folder.resolve() == (BASE_DIR / "backups").resolve()
        ):
            checks.append(
                _check_result(
                    "error",
                    "备份目录",
                    "公网环境必须把 BACKUP_FOLDER 指向持久磁盘或已挂载的备份卷",
                )
            )
        else:
            checks.append(
                _check_result(
                    "ok", "备份目录", f"可写：{backup_folder.resolve()}"
                )
            )
    except Exception as exc:
        checks.append(
            _check_result("error", "备份目录", f"不可写：{exc}")
        )

    try:
        usage = shutil.disk_usage(Path(app.config["UPLOAD_FOLDER"]))
        free_mb = usage.free // (1024 * 1024)
        if free_mb < 50:
            checks.append(
                _check_result(
                    "error",
                    "磁盘空间",
                    f"仅剩 {free_mb} MB，请先清理旧备份或附件",
                )
            )
        elif public and free_mb < 100:
            checks.append(
                _check_result(
                    "warning",
                    "磁盘空间",
                    f"仅剩 {free_mb} MB，建议保留不超过 2 份备份",
                )
            )
        else:
            checks.append(
                _check_result("ok", "磁盘空间", f"剩余 {free_mb} MB")
            )
    except OSError as exc:
        checks.append(
            _check_result("warning", "磁盘空间", f"无法读取：{exc}")
        )

    db.session.remove()
    return checks
