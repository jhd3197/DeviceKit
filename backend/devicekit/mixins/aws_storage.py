import os
import uuid
import logging
import boto3

logger = logging.getLogger(__name__)


class AwsStorageMixin:
    """S3 storage operations only (no SQS)."""

    def _get_s3_client(self):
        return boto3.client(
            's3',
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )

    def upload_file_s3(self, file_path, bucket="serviceserpapi", sub_folder="html"):
        """Upload a file to S3."""
        s3 = self._get_s3_client()
        key = f"{sub_folder}/{os.path.basename(file_path)}"
        try:
            s3.upload_file(file_path, bucket, key, ExtraArgs={'ACL': 'public-read'})
            logger.info(f"Uploaded to S3: {key}")
            return key
        except Exception as e:
            logger.error(f"S3 upload error: {e}")
            return None

    def upload_content_s3(self, content, bucket="serviceserpapi", sub_folder="html",
                          content_type="text/html", guid_id=None):
        """Upload string content to S3."""
        s3 = self._get_s3_client()
        if not guid_id:
            guid_id = str(uuid.uuid4())
        key = f"{sub_folder}/{guid_id}.html"
        try:
            s3.put_object(
                Bucket=bucket, Key=key, Body=content,
                ACL='public-read', ContentType=content_type
            )
            logger.info(f"Content uploaded to S3: {key}")
            return guid_id
        except Exception as e:
            logger.error(f"S3 content upload error: {e}")
            return None

    def get_s3_content(self, s3_uri):
        """Get content from S3 by URI."""
        s3 = self._get_s3_client()
        if s3_uri.startswith("s3://"):
            s3_uri = s3_uri[5:]
        parts = s3_uri.split("/", 1)
        try:
            response = s3.get_object(Bucket=parts[0], Key=parts[1])
            return response['Body'].read().decode('utf-8')
        except Exception as e:
            logger.error(f"Error getting S3 content: {e}")
            return None
