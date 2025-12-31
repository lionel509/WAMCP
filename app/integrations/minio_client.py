from minio import Minio
from minio.error import S3Error
from app.config import settings
import logging
import io

logger = logging.getLogger(__name__)

class MinioClientWrapper:
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            try:
                self.client.make_bucket(self.bucket)
            except S3Error as e:
                logger.error(f"Failed to create bucket: {e}")

    def upload_data(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        try:
            self.client.put_object(
                self.bucket,
                key,
                io.BytesIO(data),
                len(data),
                content_type=content_type
            )
            return True
        except S3Error as e:
            logger.error(f"MinIO Upload Error: {e}")
            return False

    def download_data(self, key: str) -> bytes | None:
        """
        Download object content as bytes. Caller is responsible for size checks.
        """
        try:
            obj = self.client.get_object(self.bucket, key)
            try:
                data = obj.read()
                return data
            finally:
                obj.close()
                obj.release_conn()
        except S3Error as e:
            logger.error(f"MinIO Download Error for {key}: {e}")
            return None

    def get_presigned_url(self, key: str, expires_sec: int = 3600):
        try:
            return self.client.presigned_get_object(self.bucket, key, expires=expires_sec)
        except S3Error as e:
             logger.error(f"MinIO Presign Error: {e}")
             return None

minio_client = MinioClientWrapper()
