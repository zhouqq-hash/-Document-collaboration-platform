"""文件存储抽象层。

默认使用本地磁盘存储，通过 ``STORAGE_BACKEND=cos`` 切换到腾讯云 COS。
切换后，``DocumentVersion.file_path`` 字段的语义从“本地文件名”变为“COS 对象 Key”，
因此业务代码不需要关心底层是本地还是云端。
"""
import os
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
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_storage.save(str(path))

    def read(self, key):
        return self._resolve(key).read_bytes()

    def delete(self, key):
        self._resolve(key).unlink(missing_ok=True)


class CosStorage:
    """把文件保存到腾讯云 COS 对象存储。"""

    def __init__(self, secret_id, secret_key, region, bucket):
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

    def save(self, file_storage, key):
        self.client.put_object(
            Bucket=self.bucket,
            Body=file_storage.read(),
            Key=key,
        )

    def read(self, key):
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].get_raw_stream().read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


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

        return CosStorage(secret_id, secret_key, region, bucket)

    return LocalStorage(app.config["UPLOAD_FOLDER"])
