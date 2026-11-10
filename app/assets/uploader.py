from hashlib import sha256
from pathlib import Path
from urllib.parse import quote
import os
import boto3
import httpx
from app.config import Settings

class AssetUploader:
    def __init__(self, settings: Settings, job_id: str, store_id: str | None = None):
        self.settings, self.job_id = settings, job_id
        self.store_id = str(store_id) if store_id else f'pending-{job_id}'
        self.local_dir = Path('/tmp/mazigho-cloner-assets') / job_id
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.blob_token = os.getenv('BLOB_READ_WRITE_TOKEN', '').strip()
        self.s3 = None
        if not self.blob_token and settings.s3_bucket and settings.aws_access_key_id and settings.aws_secret_access_key:
            self.s3 = boto3.client('s3', region_name=settings.aws_region, endpoint_url=settings.s3_endpoint_url or None, aws_access_key_id=settings.aws_access_key_id, aws_secret_access_key=settings.aws_secret_access_key)

    def _key(self, original_url: str, extension: str, thumbnail: bool = False) -> str:
        digest = sha256(original_url.encode()).hexdigest()[:24]
        suffix = '-thumb' if thumbnail else ''
        prefix = self.settings.s3_prefix.strip('/') or 'cloned'
        return f'{prefix}/{self.store_id}/{digest}{suffix}.{extension}'

    def _put_vercel_blob(self, key: str, content: bytes, content_type: str) -> str:
        pathname = quote(key, safe='/')
        response = httpx.put(
            f'https://blob.vercel-storage.com/{pathname}',
            content=content,
            headers={
                'Authorization': f'Bearer {self.blob_token}',
                'Content-Type': content_type,
                'x-api-version': '7',
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        url = data.get('url') if isinstance(data, dict) else None
        if not url:
            raise RuntimeError('Vercel Blob n’a pas renvoyé d’URL publique.')
        return str(url)

    def put(self, content: bytes, original_url: str, content_type: str = 'image/webp', extension: str = 'webp', thumbnail: bool = False) -> str:
        key = self._key(original_url, extension, thumbnail)
        if self.blob_token:
            return self._put_vercel_blob(key, content, content_type)
        if self.s3:
            self.s3.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=content, ContentType=content_type, CacheControl='public,max-age=31536000,immutable')
            if self.settings.public_cdn_url:
                return f"{self.settings.public_cdn_url.rstrip('/')}/{key}"
            return f'https://{self.settings.s3_bucket}.s3.{self.settings.aws_region}.amazonaws.com/{key}'
        target = self.local_dir / key.split('/')[-1]
        target.write_bytes(content)
        return f'/local-assets/{self.job_id}/{target.name}'
