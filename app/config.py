from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    host: str = '0.0.0.0'
    port: int = 8000
    max_clone_duration_seconds: int = 900
    max_concurrent_jobs: int = 3
    max_products: int = 2500
    request_timeout_seconds: float = 45.0
    asset_download_timeout_seconds: float = 90.0
    asset_upload_timeout_seconds: float = 120.0
    mazigho_import_timeout_seconds: float = 120.0
    mazigho_api_url: str = ''
    mazigho_api_key: str = ''
    cloner_api_key: str = ''

    # S3 or S3-compatible storage. MAZIGHO currently uses Vercel Blob;
    # these settings become active only when an S3-compatible bucket is supplied.
    aws_region: str = 'eu-west-1'
    aws_access_key_id: str = ''
    aws_secret_access_key: str = ''
    s3_bucket: str = ''
    s3_prefix: str = 'cloned/'
    s3_endpoint_url: str = ''
    public_cdn_url: str = ''
    image_max_width: int = 1600
    image_thumb_width: int = 400
    image_unchanged_threshold_bytes: int = 100 * 1024

    user_agent: str = 'Mozilla/5.0 (compatible; MAZIGHO-Site-Cloner/1.0; +https://mazigho.ch)'


@lru_cache
def get_settings() -> Settings:
    return Settings()
