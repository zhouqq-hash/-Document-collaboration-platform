"""文件存储抽象层。

默认使用本地磁盘存储，通过 ``STORAGE_BACKEND=cos`` 切换到腾讯云 COS。
切换后，``DocumentVersion.file_path`` 字段的语义从“本地文件名”变为“COS 对象 Key”，
因此业务代码不需要关心底层是本地还是云端。
"""
import os
import shutil
import tempfile
from pathlib import Path


class StorageError(Exception):
    """存储层的统一异常。"""


class LocalStorage:
    """把文件保存在本地磁盘目录下。"""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key):
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise StorageError(f"非法的存储 key: {key}")
        return path

    def save(self, file_storage, key):
        self.save_bytes(file_storage.read(), key)

    def save_bytes(self, data, key):
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def copy(self, src_key, dst_key):
        src = self._resolve(src_key)
        dst = self._resolve(dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    def read(self, key):
        return self._resolve(key).read_bytes()

    def delete(self, key):
        self._resolve(key).unlink(missing_ok=True)

    def probe(self):
        """Verify that the upload volume is writable and readable."""
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=self.root, prefix=".readiness-", delete=False
        ) as handle:
            path = Path(handle.name)
            handle.write(b"ok")
        try:
            if path.read_bytes() != b"ok":
                raise StorageError("上传目录可写但读取结果不一致")
        finally:
            path.unlink(missing_ok=True)

    def iter_keys(self):
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.name.startswith(".readiness-"):
                continue
            yield path.relative_to(self.root).as_posix()


class CosStorage:
    """把文件保存到腾讯云 COS 对象存储。"""

    def __init__(self, secret_id, secret_key, region, bucket, prefix=""):
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as exc:
            raise StorageError(
                "未安装 cos-python-sdk-v5，请先执行 "
                "python -m pip install cos-python-sdk-v5"
            ) from exc

        config = CosConfig(
            Region=region, SecretId=secret_id, SecretKey=secret_key
        )
        self.client = CosS3Client(config)
        self.bucket = bucket
        self.region = region
        self.prefix = (prefix or "").strip().strip("/")

    def _object_key(self, key):
        key = key.lstrip("/")
        return f"{self.prefix}/{key}" if self.prefix else key

    def _logical_key(self, key):
        if not self.prefix:
            return key
        prefix = f"{self.prefix}/"
        return key[len(prefix) :] if key.startswith(prefix) else None

    def save(self, file_storage, key):
        self.save_bytes(file_storage.read(), key)

    def save_bytes(self, data, key):
        self.client.put_object(
            Bucket=self.bucket,
            Body=data,
            Key=self._object_key(key),
        )

    def copy(self, src_key, dst_key):
        self.client.copy_object(
            Bucket=self.bucket,
            Key=self._object_key(dst_key),
            CopySource={
                "Bucket": self.bucket,
                "Key": self._object_key(src_key),
                "Region": self.region,
            },
        )

    def read(self, key):
        response = self.client.get_object(
            Bucket=self.bucket, Key=self._object_key(key)
        )
        return response["Body"].get_raw_stream().read()

    def delete(self, key):
        self.client.delete_object(
            Bucket=self.bucket, Key=self._object_key(key)
        )

    def probe(self):
        """Check bucket credentials with the same list permission backups need."""
        params = {"Bucket": self.bucket, "MaxKeys": 1}
        if self.prefix:
            params["Prefix"] = f"{self.prefix}/"
        try:
            self.client.list_objects(**params)
        except Exception as exc:
            raise StorageError(
                "COS 访问失败："
                f"bucket={self.bucket}, region={self.region}, "
                f"prefix={self.prefix or '(root)'}: {exc}"
            ) from exc

    def iter_keys(self):
        marker = ""
        while True:
            params = {"Bucket": self.bucket, "MaxKeys": 1000}
            if self.prefix:
                params["Prefix"] = f"{self.prefix}/"
            if marker:
                params["Marker"] = marker
            response = self.client.list_objects(**params)
            contents = response.get("Contents") or []
            for item in contents:
                key = item.get("Key")
                logical = self._logical_key(key) if key else None
                if logical:
                    yield logical
            if str(response.get("IsTruncated", "false")).lower() != "true":
                break
            marker = response.get("NextMarker") or (
                contents[-1].get("Key") if contents else ""
            )
            if not marker:
                break


def get_storage(app):
    """根据配置返回对应的存储后端。"""
    backend = (
        app.config.get("STORAGE_BACKEND")
        or os.environ.get("STORAGE_BACKEND")
        or "local"
    ).strip().lower()

    if backend == "cos":
        secret_id = app.config.get("COS_SECRET_ID") or os.environ.get(
            "COS_SECRET_ID"
        )
        secret_key = app.config.get("COS_SECRET_KEY") or os.environ.get(
            "COS_SECRET_KEY"
        )
        region = app.config.get("COS_REGION") or os.environ.get("COS_REGION")
        bucket = app.config.get("COS_BUCKET") or os.environ.get("COS_BUCKET")

        missing = [
            name
            for name, value in (
                ("COS_SECRET_ID", secret_id),
                ("COS_SECRET_KEY", secret_key),
                ("COS_REGION", region),
                ("COS_BUCKET", bucket),
            )
            if not value
        ]
        if missing:
            raise StorageError(
                "切换 COS 存储缺少配置: " + ", ".join(missing)
            )

        prefix = app.config.get("COS_KEY_PREFIX") or os.environ.get(
            "COS_KEY_PREFIX", ""
        )
        return CosStorage(secret_id, secret_key, region, bucket, prefix)

    return LocalStorage(app.config["UPLOAD_FOLDER"])
