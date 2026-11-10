from dataclasses import dataclass
from io import BytesIO
from PIL import Image
import httpx


@dataclass
class OptimizedAsset:
    content: bytes
    content_type: str
    extension: str
    thumbnail: bytes | None = None
    thumbnail_content_type: str | None = None


def _has_transparency(image: Image.Image) -> bool:
    return image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info)


def _content_type(image: Image.Image, response_type: str) -> tuple[str, str]:
    fmt = (image.format or '').upper()
    if fmt == 'JPEG': return 'image/jpeg', 'jpg'
    if fmt == 'PNG': return 'image/png', 'png'
    if fmt == 'GIF': return 'image/gif', 'gif'
    if fmt == 'WEBP': return 'image/webp', 'webp'
    if response_type in {'image/svg+xml', 'image/gif', 'image/png', 'image/jpeg', 'image/webp'}:
        return response_type, response_type.split('/')[-1].replace('svg+xml', 'svg')
    return 'application/octet-stream', 'bin'


def _thumbnail(image: Image.Image, width: int) -> bytes | None:
    if image.format in {'SVG', 'GIF'} or image.width <= width:
        return None
    thumb = image.copy()
    thumb.thumbnail((width, width), Image.Resampling.LANCZOS)
    output = BytesIO()
    if _has_transparency(thumb):
        thumb.save(output, format='PNG', optimize=True)
    else:
        thumb.convert('RGB').save(output, format='WEBP', quality=82, method=6)
    return output.getvalue()


async def download_and_optimize(url: str, client: httpx.AsyncClient, max_width: int = 1600, thumb_width: int = 400, unchanged_threshold: int = 100 * 1024) -> OptimizedAsset | None:
    if not url or not url.startswith(('http://', 'https://')): return None
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        raw = response.content
        content_type = response.headers.get('content-type', '').split(';', 1)[0].lower()
        if content_type == 'image/svg+xml' or content_type == 'image/gif' or len(raw) < unchanged_threshold:
            return OptimizedAsset(raw, content_type or 'application/octet-stream', content_type.split('/')[-1].replace('svg+xml', 'svg') or 'bin')
        image = Image.open(BytesIO(raw))
        original_type, original_ext = _content_type(image, content_type)
        thumb = _thumbnail(image, thumb_width)
        if original_type == 'image/png' and _has_transparency(image):
            image.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
            output = BytesIO(); image.save(output, format='PNG', optimize=True)
            return OptimizedAsset(output.getvalue(), 'image/png', 'png', thumb, 'image/png' if thumb else None)
        if original_type not in {'image/jpeg', 'image/png'}:
            return OptimizedAsset(raw, original_type, original_ext, thumb, 'image/webp' if thumb else None)
        image.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
        output = BytesIO(); image.convert('RGB').save(output, format='WEBP', quality=84, method=6)
        return OptimizedAsset(output.getvalue(), 'image/webp', 'webp', thumb, 'image/webp' if thumb else None)
    except (httpx.HTTPError, OSError, ValueError):
        return None
