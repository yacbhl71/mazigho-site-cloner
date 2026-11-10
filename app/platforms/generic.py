import re
from bs4 import BeautifulSoup
from .base import BaseExtractor

class GenericExtractor(BaseExtractor):
    async def extract(self) -> dict:
        html = (await self.client.get(self.base_url)).text
        soup = BeautifulSoup(html, 'lxml')
        products = []
        for card in soup.select('[class*="product"], [class*="card"]')[:2500]:
            title = card.select_one('h1,h2,h3,h4,[class*="title"]')
            image = card.select_one('img')
            text = card.get_text(' ', strip=True)
            price = re.search(r'(?:€|\$|£)\s?[\d.,]+|[\d.,]+\s?(?:€|\$|£)', text)
            if title or price:
                products.append({'title': title.get_text(' ', strip=True) if title else 'Produit', 'description': text[:1000], 'price_text': price.group(0) if price else '', 'images': [{'src': image.get('src')}] if image and image.get('src') else []})
        navigation = [{'label': a.get_text(' ', strip=True), 'href': a.get('href')} for a in soup.select('nav a, header a') if a.get_text(strip=True)][:50]
        return {'products': products, 'collections': [], 'pages': [], 'navigation': navigation}
