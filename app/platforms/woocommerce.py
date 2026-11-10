from typing import Any
from urllib.parse import urlsplit, urlunsplit
from bs4 import BeautifulSoup
from .base import BaseExtractor


class WooCommerceExtractor(BaseExtractor):
    def __init__(self, base_url: str, client: Any, page: Any | None = None):
        super().__init__(base_url, client, page)
        parts = urlsplit(base_url)
        self.origin = urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")

    async def _products_from_store_api(self) -> list[dict[str, Any]]:
        response = await self.client.get(f"{self.origin}/wp-json/wc/store/v1/products?per_page=100")
        if response.status_code >= 400:
            return []
        raw = response.json()
        products = []
        for product in raw if isinstance(raw, list) else []:
            prices = product.get("prices") or {}
            minor_unit = int(prices.get("currency_minor_unit") or 2)
            divisor = 10 ** minor_unit
            variants = []
            for variation in product.get("variations") or []:
                if isinstance(variation, dict):
                    variation_prices = variation.get("prices") or {}
                    variants.append({
                        "title": variation.get("name") or "Variante",
                        "price": float(variation_prices.get("price") or 0) / divisor,
                        "sku": variation.get("sku"),
                    })
            products.append({
                "name": product.get("name") or "Produit",
                "title": product.get("name") or "Produit",
                "description": product.get("description") or product.get("short_description") or "",
                "price": float(prices.get("price") or 0) / divisor,
                "compare_at_price": float(prices.get("regular_price") or 0) / divisor,
                "currency": prices.get("currency_code") or "EUR",
                "images": [{"src": image.get("src")} for image in product.get("images") or [] if image.get("src")],
                "variants": variants,
                "product_type": ", ".join(category.get("name", "") for category in product.get("categories") or [] if category.get("name")),
                "vendor": "",
            })
        return products

    async def extract(self) -> dict[str, Any]:
        products = await self._products_from_store_api()
        if not products:
            response = await self.client.get(f"{self.origin}/wp-json/wc/v3/products?per_page=100")
            if response.status_code < 400 and isinstance(response.json(), list):
                products = response.json()
            else:
                soup = BeautifulSoup((await self.client.get(self.origin)).text, "lxml")
                for card in soup.select(".product, li.product, [class*='product']")[:2500]:
                    title = card.select_one(".woocommerce-loop-product__title, .product-title, h2, h3")
                    price = card.select_one(".price")
                    image = card.select_one("img")
                    products.append({
                        "name": title.get_text(" ", strip=True) if title else "Produit",
                        "price_html": price.get_text(" ", strip=True) if price else "",
                        "images": [{"src": image.get("src")} ] if image and image.get("src") else [],
                    })
        page_response = await self.client.get(f"{self.origin}/wp-json/wp/v2/pages?per_page=100")
        pages = page_response.json() if page_response.status_code < 400 and isinstance(page_response.json(), list) else []
        return {"products": products, "pages": pages, "collections": [], "navigation": []}
