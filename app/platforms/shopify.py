import asyncio
from typing import Any
from urllib.parse import urljoin
from .base import BaseExtractor


class ShopifyExtractor(BaseExtractor):
    async def _all(self, path: str, key: str) -> list[dict[str, Any]]:
        items, page = [], 1
        while len(items) < 2500:
            for attempt in range(3):
                response = await self.client.get(urljoin(self.base_url + '/', f'{path}?page={page}&limit=250'))
                if response.status_code != 429 or attempt == 2:
                    break
                retry_after = response.headers.get('retry-after', '5')
                try: delay = min(max(float(retry_after), 1.0), 30.0)
                except ValueError: delay = 5.0
                await asyncio.sleep(delay)
            if response.status_code in (404, 401): break
            response.raise_for_status()
            batch = response.json().get(key, [])
            if not batch: break
            items.extend(batch)
            if len(batch) < 250: break
            page += 1
        return items[:2500]

    async def _cms_pages(self) -> list[dict[str, Any]]:
        raw_pages = await self._all('pages.json', 'pages')
        return [{
            'title': str(page.get('title') or page.get('handle') or 'Page importée')[:255],
            'handle': str(page.get('handle') or f'page-{index + 1}')[:180],
            'body_html': str(page.get('body_html') or '')[:10000],
            'updated_at': page.get('updated_at'),
            'published_at': page.get('published_at'),
            'author': page.get('author'),
        } for index, page in enumerate(raw_pages)]

    async def extract(self) -> dict[str, Any]:
        products = await self._all('products.json', 'products')
        collections = await self._all('collections.json', 'collections')
        pages = await self._cms_pages()
        navigation = []
        if self.page:
            navigation = await self.page.evaluate("""() => Array.from(document.querySelectorAll('nav a, header a')).slice(0,50).map(a => ({label:(a.innerText||a.textContent||'').trim(), href:a.href})).filter(x=>x.label)""")
        return {'products': products, 'collections': collections, 'pages': pages, 'navigation': navigation}
