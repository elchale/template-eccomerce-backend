import base64
import json
import os
import uuid
from typing import Optional, List
from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account
import logging

logger = logging.getLogger(__name__)


class GCSUploader:
    """Google Cloud Storage file uploader utility"""

    def __init__(self):
        self.bucket_name = settings.GCS_BUCKET_NAME
        self.project_id = settings.GCS_PROJECT_ID
        self._client = None
        self._bucket = None

    def _build_credentials(self):
        """
        Resolve credentials using a priority chain:
        1. GCS_CREDENTIALS_JSON — base64-encoded JSON string (Railway / any PaaS)
        2. GCS_CREDENTIALS_PATH — local file path (development)
        3. Application Default Credentials (GCP-hosted environments)
        """
        credentials_json = getattr(settings, 'GCS_CREDENTIALS_JSON', '')
        credentials_path = getattr(settings, 'GCS_CREDENTIALS_PATH', '')

        if credentials_json:
            info = json.loads(base64.b64decode(credentials_json).decode('utf-8'))
            return service_account.Credentials.from_service_account_info(info)

        if credentials_path and os.path.exists(credentials_path):
            return service_account.Credentials.from_service_account_file(credentials_path)

        return None  # falls back to Application Default Credentials

    @property
    def client(self):
        """Lazy initialization of GCS client"""
        if self._client is None:
            credentials = self._build_credentials()
            self._client = storage.Client(
                credentials=credentials,
                project=self.project_id,
            )
        return self._client

    @property
    def bucket(self):
        """Lazy initialization of GCS bucket"""
        if self._bucket is None:
            self._bucket = self.client.bucket(self.bucket_name)
        return self._bucket

    def upload_file(self, file, folder: str = "uploads", filename: Optional[str] = None) -> str:
        """
        Upload a file to Google Cloud Storage

        Args:
            file: Django UploadedFile object
            folder: Folder path in the bucket (default: "uploads")
            filename: Custom filename (optional, will generate UUID if not provided)

        Returns:
            str: Public URL of the uploaded file

        Raises:
            Exception: If upload fails
        """
        try:
            # Generate filename if not provided
            if not filename:
                file_extension = os.path.splitext(file.name)[1]
                filename = f"{uuid.uuid4()}{file_extension}"

            # Create blob path
            blob_name = f"{folder}/{filename}"
            blob = self.bucket.blob(blob_name)

            # Set content type based on file
            content_type = file.content_type or 'application/octet-stream'
            blob.content_type = content_type

            # Upload file
            file.seek(0)  # Reset file pointer
            blob.upload_from_file(file, content_type=content_type)

            # Make blob publicly readable
            blob.make_public()

            logger.info(f"Successfully uploaded file to GCS: {blob_name}")
            return blob.public_url

        except Exception as e:
            logger.error(f"Failed to upload file to GCS: {str(e)}")
            raise Exception(f"File upload failed: {str(e)}")

    def delete_file(self, file_url: str) -> bool:
        """
        Delete a file from Google Cloud Storage using its public URL

        Args:
            file_url: Public URL of the file to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            # Extract blob name from URL
            # URL format: https://storage.googleapis.com/bucket-name/path/to/file
            if f"storage.googleapis.com/{self.bucket_name}/" in file_url:
                blob_name = file_url.split(f"storage.googleapis.com/{self.bucket_name}/")[1]
                blob = self.bucket.blob(blob_name)
                blob.delete()
                logger.info(f"Successfully deleted file from GCS: {blob_name}")
                return True
            else:
                logger.warning(f"Invalid GCS URL format: {file_url}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete file from GCS: {str(e)}")
            return False


# Global instance
gcs_uploader = GCSUploader()


def upload_file(file, folder: str = "uploads", filename: Optional[str] = None,
                allowed_types: Optional[List[str]] = None, max_size_mb: Optional[int] = None) -> str:
    """
    Generic file upload function with optional validation

    Args:
        file: Django UploadedFile object
        folder: Folder path in the bucket (default: "uploads")
        filename: Custom filename (optional, will generate UUID if not provided)
        allowed_types: List of allowed MIME types (optional)
        max_size_mb: Maximum file size in MB (optional)

    Returns:
        str: Public URL of the uploaded file

    Raises:
        Exception: If file validation fails or upload fails
    """
    # Validate file type if specified
    if allowed_types and file.content_type not in allowed_types:
        raise Exception(f"Invalid file type. Allowed types: {', '.join(allowed_types)}")

    # Validate file size if specified
    if max_size_mb:
        max_size = max_size_mb * 1024 * 1024  # Convert MB to bytes
        if file.size > max_size:
            raise Exception(f"File too large. Maximum size: {max_size_mb}MB, got: {file.size / (1024*1024):.1f}MB")

    return gcs_uploader.upload_file(file, folder=folder, filename=filename)


def upload_image(file, folder: str = "images", filename: Optional[str] = None, max_size_mb: int = 5) -> str:
    """
    Upload an image file with validation

    Args:
        file: Django UploadedFile object
        folder: Folder path in the bucket (default: "images")
        filename: Custom filename (optional, will generate UUID if not provided)
        max_size_mb: Maximum file size in MB (default: 5MB)

    Returns:
        str: Public URL of the uploaded file

    Raises:
        Exception: If file validation fails
    """
    allowed_image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif']
    return upload_file(file, folder=folder, filename=filename,
                      allowed_types=allowed_image_types, max_size_mb=max_size_mb)


def upload_document(file, folder: str = "documents", filename: Optional[str] = None, max_size_mb: int = 10) -> str:
    """
    Upload a document file with validation

    Args:
        file: Django UploadedFile object
        folder: Folder path in the bucket (default: "documents")
        filename: Custom filename (optional, will generate UUID if not provided)
        max_size_mb: Maximum file size in MB (default: 10MB)

    Returns:
        str: Public URL of the uploaded file

    Raises:
        Exception: If file validation fails
    """
    allowed_document_types = [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/plain',
        'text/csv'
    ]
    return upload_file(file, folder=folder, filename=filename,
                      allowed_types=allowed_document_types, max_size_mb=max_size_mb)


def delete_file_from_url(file_url: str) -> bool:
    """
    Delete a file from GCS using its URL

    Args:
        file_url: Public URL of the file to delete

    Returns:
        bool: True if deletion was successful, False otherwise
    """
    if not file_url:
        return True
    return gcs_uploader.delete_file(file_url)


def generate_secure_filename(original_filename: str, prefix: Optional[str] = None) -> str:
    """
    Generate a secure filename with UUID

    Args:
        original_filename: Original filename from upload
        prefix: Optional prefix for the filename

    Returns:
        str: Secure filename with UUID
    """
    file_extension = os.path.splitext(original_filename)[1].lower()
    uuid_part = uuid.uuid4().hex[:8]

    if prefix:
        # Sanitize prefix for filename
        safe_prefix = "".join(c for c in prefix if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_prefix = safe_prefix.replace(' ', '_').lower()
        return f"{safe_prefix}_{uuid_part}{file_extension}"
    else:
        return f"{uuid_part}{file_extension}"
