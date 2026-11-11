from datetime import datetime, timezone
from html import escape
import re
from typing import Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Comment

ESSENTIAL_KEYWORDS = (
    "about", "contact", "faq", "shipping", "returns", "privacy", "terms",
    "legal", "policy", "policies", "cgv", "livraison", "retours",
)
ARCHIVE_KEYWORDS = ("ambassador", "affiliate", "test", "copy", "old", "backup")
ARCHIVE_YEARS = tuple(str(year) for year in range(2018, 2024))


def _price(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_href(value: Any) -> str | None:
    href = str(value or "").strip()
    if href.startswith("/") or href.lower().startswith("https://"):
        return href
    return None


def _variant_options(variant: dict[str, Any], product: dict[str, Any]) -> dict[str, str]:
    options: dict[str, str] = {}
    for index, value in enumerate((variant.get("option1"), variant.get("option2"), variant.get("option3")), start=1):
        if value:
            names = product.get("options") or []
            name = names[index - 1].get("name") if index <= len(names) and isinstance(names[index - 1], dict) else f"Option {index}"
            options[str(name)[:100]] = str(value)[:100]
    raw = variant.get("options")
    if isinstance(raw, dict):
        options.update({str(key)[:100]: str(value)[:100] for key, value in raw.items() if value is not None})
    return options


def _sanitize_variant(variant: dict[str, Any], product: dict[str, Any], assets: dict[str, str]) -> dict[str, Any]:
    image = variant.get("image")
    image_url = image.get("src") if isinstance(image, dict) else variant.get("imageUrl")
    if image_url:
        image_url = assets.get(image_url, image_url)
    result: dict[str, Any] = {"title": str(variant.get("title") or variant.get("name") or "Variante")[:160], "price": _price(variant.get("price")), "options": _variant_options(variant, product)}
    if variant.get("sku"): result["sku"] = str(variant["sku"])[:100]
    if image_url and _safe_href(image_url): result["imageUrl"] = image_url
    return result


def _classify_page(handle: str, title: str, text: str) -> str:
    haystack = f"{handle} {title}".lower()
    if any(keyword in haystack for keyword in ESSENTIAL_KEYWORDS):
        return "essentielle"
    signals = 0
    if any(year in haystack for year in ARCHIVE_YEARS): signals += 1
    if any(keyword in haystack for keyword in ARCHIVE_KEYWORDS): signals += 1
    if len(text.strip()) < 100: signals += 1
    return "archivée" if signals >= 2 else "à vérifier"


def _clean_page_html(raw_html: str, source_url: str, assets: dict[str, str]) -> tuple[str, bool, str]:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in soup.find_all(["script", "style", "iframe", "object", "embed", "form"]): tag.decompose()
    for element in soup.find_all(True):
        for attribute in list(element.attrs):
            if attribute.lower().startswith("on"): del element.attrs[attribute]
        if element.name == "a":
            href = str(element.get("href") or "")
            if any(blocked in href.lower() for blocked in ("/admin/", "/cart", "/checkout")):
                element["href"] = "#"
        if element.name == "img":
            src = str(element.get("src") or "")
            if src.startswith("//"): src = "https:" + src
            absolute = urljoin(source_url, src)
            element["src"] = assets.get(src, assets.get(absolute, absolute if absolute.startswith("https://") else ""))
            if not element.get("alt"): element["alt"] = "Image importée"
    html = "".join(str(child) for child in soup.body.contents) if soup.body else str(soup)
    html = html[:10000]
    text = soup.get_text(" ", strip=True)
    complex_html = bool(soup.find(["table", "ul", "ol"]) or len(html) > 4000)
    return html, complex_html, text


def rebuild(user_id: str, name: str, source_url: str, platform: str, extracted: dict, analysis: dict, assets: dict[str, str]) -> dict:
    catalog = []
    for index, product in enumerate(extracted.get("products", [])):
        images = product.get("images", []) or []
        image_urls = [img.get("src") or img.get("url") for img in images if isinstance(img, dict)]
        image_urls = [assets.get(url, url) for url in image_urls if url and _safe_href(url)]
        variants = product.get("variants", []) or []
        catalog.append({"id": f"prod_{index + 1:03d}", "title": str(product.get("title") or product.get("name") or "Produit importé")[:200], "description": str(product.get("body_html") or product.get("description") or "")[:10000], "price": _price((variants[0] if variants else {}).get("price") if variants else product.get("price")), "compareAtPrice": _price((variants[0] if variants else {}).get("compare_at_price") if variants else product.get("compare_at_price")), "currency": "EUR", "images": image_urls, "variants": [_sanitize_variant(variant, product, assets) for variant in variants if isinstance(variant, dict)], "tags": product.get("tags", []) if isinstance(product.get("tags", []), list) else str(product.get("tags", "")).split(", "), "type": str(product.get("product_type", ""))[:100], "vendor": str(product.get("vendor", ""))[:160]})
    sections = analysis.get("sections", ["header", "hero", "product-grid", "footer"])
    visual_blocks = analysis.get("visual_blocks", []) if isinstance(analysis.get("visual_blocks", []), list) else []
    home_blocks = []
    # Keep every rendered section, not only the first section of each type.
    # Shopify themes frequently contain several anonymous/custom sections whose
    # order is essential to the visual composition.
    source_blocks = visual_blocks or [{"type": kind, "position": index} for index, kind in enumerate(sections)]
    for i, block in enumerate(source_blocks[:32]):
        kind = str(block.get("type") or "custom")
        props = {key: value for key, value in block.items() if key not in {"id", "type", "position"}}
        if props.get("imageUrl"):
            raw_image = str(props["imageUrl"])
            props["imageUrl"] = assets.get(raw_image, raw_image)
        if isinstance(props.get("galleryItems"), list):
            props["galleryItems"] = [
                {**item, "imageUrl": assets.get(str(item.get("imageUrl")), item.get("imageUrl"))}
                for item in props["galleryItems"]
                if isinstance(item, dict)
            ]
        component = "".join(part.title() for part in kind.split("-")) + "Section"
        home_blocks.append({"id": f"blk_{i + 1:03d}", "type": kind, "component": component, "props": props})
    pages: dict[str, dict[str, Any]] = {"home": {"title": "Accueil", "handle": "home", "category": "essentielle", "blocks": home_blocks, "reviewRequired": False}}
    for index, page in enumerate(extracted.get("pages", [])):
        handle = str(page.get("handle") or f"page-{index + 1}").strip()[:180] or f"page-{index + 1}"
        if handle in pages: handle = f"{handle}-{index + 1}"[:180]
        title = str(page.get("title") or handle)[:255]
        body_html, complex_html, text = _clean_page_html(str(page.get("body_html") or ""), source_url, assets)
        category = _classify_page(handle, title, text)
        page_url = urljoin(source_url.rstrip("/") + "/", f"pages/{handle}")
        pages[handle] = {"title": title, "handle": handle, "category": category, "source_url": page_url, "original_updated_at": page.get("updated_at"), "reviewRequired": complex_html, "blocks": [{"id": f"blk_{handle[:30]}_1", "type": "custom-html" if complex_html else "rich-text", "component": "CustomHTML" if complex_html else "RichText", "props": {"content": body_html}, "reviewRequired": complex_html}]}
    navigation = []
    for item in extracted.get("navigation", []):
        if isinstance(item, dict):
            href = _safe_href(item.get("href")); label = str(item.get("label") or "").strip()[:80]
            if href and label: navigation.append({"label": label, "href": href})
    return {"user_id": user_id, "project_name": name, "source_url": source_url, "platform": platform, "theme": analysis.get("design_system", {}), "pages": pages, "catalog": catalog, "navigation": navigation[:50], "settings": {"currency": "EUR", "clonedFrom": source_url, "clonedPlatform": platform, "clonedAt": datetime.now(timezone.utc).isoformat()}}
