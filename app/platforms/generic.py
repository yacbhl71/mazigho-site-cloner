import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .base import BaseExtractor

class GenericExtractor(BaseExtractor):
    async def extract(self) -> dict:
        # Prefer the Playwright-rendered DOM when available. Modern storefronts
        # often ship only an empty React root over HTTP and populate the product
        # cards client-side; parsing the raw response alone loses the catalogue.
        if self.page is not None:
            try:
                html = await self.page.content()
            except Exception:
                html = (await self.client.get(self.base_url)).text
        else:
            html = (await self.client.get(self.base_url)).text
        soup = BeautifulSoup(html, 'lxml')
        products = []
        seen_product_urls = set()
        cards = soup.select('[class*="product"], [class*="card"]')
        # Generic MAZIGHO-style storefronts expose canonical product links even
        # when their utility classes do not contain the words product/card.
        for link in soup.select('a[href*="/produit/"], a[href*="/product/"]'):
            parent = link
            for _ in range(4):
                if parent.parent is None:
                    break
                parent = parent.parent
                if parent.name in {'article', 'li'} or parent.find('img'):
                    break
            cards.append(parent)
        for card in cards[:2500]:
            title = card.select_one('h1,h2,h3,h4,[class*="title"]')
            image = card.select_one('img')
            text = card.get_text(' ', strip=True)
            link = card.select_one('a[href*="/produit/"], a[href*="/product/"]')
            product_url = urljoin(self.base_url + '/', link.get('href')) if link and link.get('href') else ''
            if product_url and product_url in seen_product_urls:
                continue
            price = re.search(r'(?:€|\$|£|CHF)\s?[\d.,]+|[\d.,]+\s?(?:€|\$|£|CHF)', text, re.I)
            if title or price:
                if product_url:
                    seen_product_urls.add(product_url)
                image_url = urljoin(self.base_url + '/', image.get('src')) if image and image.get('src') else ''
                products.append({'title': title.get_text(' ', strip=True) if title else 'Produit', 'description': text[:1000], 'price_text': price.group(0) if price else '', 'url': product_url, 'images': [{'src': image_url}] if image_url else []})
        navigation = [{'label': a.get_text(' ', strip=True), 'href': a.get('href')} for a in soup.select('nav a, header a') if a.get_text(strip=True)][:50]
        return {'products': products, 'collections': [], 'pages': [], 'navigation': navigation}
