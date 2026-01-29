"""
MinIO storage service for document file operations
"""

import io
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from minio import Minio
from minio.error import S3Error
import logging
from app.core.settings import settings
from app.core.exceptions import (
    MinIOUploadException,
    MinIODownloadException,
    MinIODeleteException,
    StorageException
)

logger = logging.getLogger(__name__)

class StorageService:
    """Service for managing document storage in MinIO"""

    def __init__(self):
        """Initialize MinIO client"""
        self.endpoint = settings.minio.endpoint
        self.access_key = settings.minio.root_user
        self.secret_key = settings.minio.root_password
        self.bucket_name = settings.minio.bucket
        self.secure = settings.minio.secure

        # Initialize MinIO client
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created MinIO bucket: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Error checking/creating bucket: {e}")
            raise StorageException(f"Failed to create bucket: {self.bucket_name}", details={"reason": str(e)})  

    def generate_object_key(self, filename: str) -> str:
        """
        Generate unique object key for file

        Format: YYYY/MM/DD/{uuid}_{original_filename}

        Args:
            filename: Original filename

        Returns:
            Object key (path in MinIO)
        """
        now = datetime.utcnow()
        date_path = now.strftime("%Y/%m/%d")
        unique_id = str(uuid4())[:8]

        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")

        return f"{date_path}/{unique_id}_{safe_filename}"

    def upload_file(
        self,
        file_data: bytes,
        filename: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload file to MinIO

        Args:
            file_data: File content as bytes
            filename: Original filename
            content_type: MIME type (optional)

        Returns:
            Object key (path in MinIO)

        Raises:
            S3Error: If upload fails
        """
        object_key = self.generate_object_key(filename)

        # Determine content type if not provided
        if content_type is None:
            if filename.endswith('pdf'):
                content_type = 'application/pdf'
            elif filename.endswith('.docx'):
                content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif filename.endswith('.txt'):
                content_type = 'text/plain'
            elif filename.endswith('.md'):
                content_type = 'text/markdown'
            else:
                content_type = 'application/octet-stream'

        try:
            # Upload to MinIO
            self.client.put_object(
                self.bucket_name,
                object_key,
                io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type
            )

            return object_key

        except S3Error as e:
            raise MinIOUploadException(filename, str(e))

    def download_file(self, object_key: str) -> bytes:
        """
        Download file from MinIO

        Args:
            object_key: Object key in MinIO

        Returns:
            File content as bytes

        Raises:
            S3Error: If download fails
        """
        try:
            response = self.client.get_object(self.bucket_name, object_key)
            data = response.read()
            response.close()
            return data

        except S3Error as e:
            raise MinIODownloadException(object_key, str(e))

    def delete_file(self, object_key: str) -> bool:
        """
        Delete file from MinIO

        Args:
            object_key: Object key in MinIO

        Returns:
            True if successful

        Raises:
            S3Error: If deletion fails
        """
        try:
            self.client.remove_object(self.bucket_name, object_key)
            return True
        except S3Error as e:
            raise MinIODeleteException(object_key, str(e))

    def file_exists(self, object_key: str) -> bool:
        """
        Check if file exists in MinIO

        Args:
            object_key: Object key in MinIO

        Returns:
            True if file exists
        """
        try:
            self.client.stat_object(self.bucket_name, object_key)
            return True
        except S3Error:
            return False

    def get_file_info(self, object_key: str) -> dict:
        """
        Get file metadata from MinIO

        Args:
            object_key: Object key in MinIO

        Returns:
            Dictionary with file metadata
        """
        try:
            stat = self.client.stat_object(self.bucket_name, object_key)
            return {
                "object_key": object_key,
                "size": stat.size,
                "last_modified": stat.last_modified,
                "content_type": stat.content_type,
                "etag": stat.etag
            }
        except S3Error as e:
            raise StorageException(f"Failed to get file info: {object_key}", details={"reason": str(e)})

    def list_files(self, prefix: str = "") -> list[dict]:
        """
        List files in bucket

        Args:
            prefix: Filter by prefix (optional)

        Returns:
            List of file metadata dictionaries
        """
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            return [
                {
                    "object_key": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified
                }
                for obj in objects
            ]
        except S3Error as e:
            raise StorageException(f"Failed to list files", details={"prefix": prefix, "reason": str(e)})

    def get_presigned_url(
        self,
        object_key: str,
        expiry_seconds: int = 3600
    ) -> str:
        """
        Generate a presigned URL for temporary file access

        Args:
            object_key: Object key in MinIO
            expiry_seconds: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL (valid for specified duration)
        """
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_key,
                expires=timedelta(seconds=expiry_seconds)
            )
            return url
        except S3Error as e:
            raise StorageException(f"Failed to generate presigned URL", details={"object_key": object_key, "reason": str(e)})


# Global storage service instance
storage_service = StorageService()
