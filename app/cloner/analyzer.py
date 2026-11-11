from collections import Counter
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

SECTION_RULES = {
    "header": ("header", "nav", "menu"),
    "hero": ("hero", "banner", "masthead"),
    "product-grid": ("product", "collection", "catalog", "shop"),
    "testimonials": ("testimonial", "review"),
    "cta": ("cta", "call-to-action", "subscription", "club"),
    "about": ("about", "story", "nutrition", "fuel"),
    "newsletter": ("newsletter", "subscribe"),
    "footer": ("footer",),
}

KNOWN_TYPES = set(SECTION_RULES)


def _text(node: Any, limit: int = 900) -> str:
    return " ".join(node.get_text(" ", strip=True).split())[:limit]


def _absolute_url(value: Any, base_url: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    if not raw:
        return ""
    return urljoin(base_url, raw) if base_url else raw


def _section_type(node: Any, index: int, text: str) -> str:
    class_marker = f"{node.name} {node.get('id', '')} {' '.join(node.get('class', []))}".lower()
    marker = f"{class_marker} {text}".lower()
    # Prefer strong textual cues before generic tokens such as "product" that
    # can occur inside an otherwise unrelated hero paragraph.
    if any(token in marker for token in ("★★★★★", "testimonial", "review")):
        return "testimonials"
    if "real food. balanced energy" in marker or "shop now" in marker and index >= 2:
        return "hero"
    if "subscription box" in marker or "join the club" in marker:
        return "cta"
    if "sign up to our newsletter" in marker or "email address" in marker:
        return "newsletter"
    for kind, tokens in SECTION_RULES.items():
        if any(token in marker for token in tokens):
            return kind

    # Shopify themes often omit semantic classes. Keep the visual order as a
    # reliable fallback for the first rendered sections of the home page.
    if index <= 1:
        return "header"
    if index == 2:
        return "hero"
    if any(token in marker for token in ("customer", "quote")):
        return "testimonials"
    return "custom"


def _links(node: Any, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for link in node.find_all("a", href=True)[:12]:
        label = _text(link, 120)
        href = _absolute_url(link.get("href"), base_url)
        if label and href:
            links.append({"label": label, "href": href})
    return links


def _gallery(node: Any, base_url: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, image in enumerate(node.find_all("img")[:12]):
        source = image.get("src") or image.get("data-src") or image.get("data-srcset")
        if not source:
            continue
        if isinstance(source, str) and "," in source:
            source = source.split(",", 1)[0].strip().split(" ", 1)[0]
        image_url = _absolute_url(source, base_url)
        if not image_url.startswith("http"):
            continue
        parent = image.find_parent("a")
        label = _text(parent, 100) if parent else str(image.get("alt") or "").strip()
        items.append({
            "id": f"gallery-{index + 1}",
            "label": label or f"Visuel {index + 1}",
            "imageUrl": image_url,
            "imageAlt": str(image.get("alt") or label or "Visuel importé")[:180],
            "href": _absolute_url(parent.get("href"), base_url) if parent else "",
        })
    return items


def _props(node: Any, kind: str, base_url: str, index: int) -> dict[str, Any]:
    headings = node.find_all(["h1", "h2", "h3", "h4"], limit=3)
    heading = headings[0] if headings else None
    paragraphs = [p for p in node.find_all(["p", "div"]) if _text(p, 1000)]
    title = _text(heading, 220) if heading else ""
    full_text = _text(node, 1400)
    text = _text(paragraphs[0], 900) if paragraphs else full_text
    if title and text == title:
        text = full_text.replace(title, "", 1).strip()[:900]

    images = node.find_all("img")
    image_url = ""
    image_alt = ""
    if images:
        image = images[0]
        image_url = _absolute_url(image.get("src") or image.get("data-src"), base_url)
        image_alt = str(image.get("alt") or title or "Visuel importé")[:180]

    links = _links(node, base_url)
    gallery_items = _gallery(node, base_url)
    button = next((link for link in links if link["label"].lower() not in {"previous slide", "next slide"}), None)

    if kind == "hero":
        layout, theme = "spotlight", "dark"
    elif kind == "testimonials":
        layout, theme = "quote", "dark"
    elif len(gallery_items) >= 4:
        layout, theme = "roundGallery", "soft"
    elif image_url:
        layout, theme = "split", "light"
    else:
        layout, theme = "banner", "light"

    return {
        "eyebrow": "" if kind in {"header", "footer"} else ("Présentation" if kind == "hero" else kind.replace("-", " ").title()),
        "title": title or (full_text[:180] if full_text else ""),
        "text": text,
        "imageUrl": image_url,
        "imageAlt": image_alt,
        "links": links,
        "buttonLabel": button["label"] if button else "",
        "buttonUrl": button["href"] if button else "",
        "galleryItems": gallery_items,
        "layout": layout,
        "theme": theme,
        "sourceIndex": index,
    }


def analyze(html: str, base_url: str = "") -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    sections: list[str] = []
    visual_blocks: list[dict[str, Any]] = []

    # Prefer actual section nodes from the rendered DOM. This is important for
    # Shopify themes whose visual composition is assembled client-side.
    section_candidates = soup.find_all("section")
    # A modern Shopify homepage normally has one section per visual module.
    # In that case sections are the source of truth; collecting header/nav/footer
    # descendants as well would duplicate the rendered composition.
    candidates = section_candidates if len(section_candidates) >= 2 else soup.find_all(["header", "main", "section", "footer", "nav"])
    # Some themes render their sections as divs with semantic class names.
    # Include those nodes while avoiding a second pass over every layout div.
    for node in soup.find_all("div"):
        marker = f"{node.get('id', '')} {' '.join(node.get('class', []))}".lower()
        # Do not collect nested layout divs from a real section: they would
        # duplicate the same hero/testimonial several dozen times. Keep only
        # explicit semantic blocks that live outside a section (e.g. the
        # compact product-grid fixture used by generic sites).
        explicit = any(token in marker for token in ("product-grid", "product-grid", "hero-section", "testimonial-section", "newsletter-section"))
        if explicit and node.find_parent("section") is None:
            candidates.append(node)

    for index, node in enumerate(candidates[:32]):
        text = _text(node)
        marker = f"{node.name} {node.get('id', '')} {' '.join(node.get('class', []))}".lower()
        has_section_marker = any(token in marker for tokens in SECTION_RULES.values() for token in tokens)
        if len(text) < 12 and not node.find("img") and not has_section_marker:
            continue
        kind = _section_type(node, index, text)
        if kind not in sections:
            sections.append(kind)
        props = _props(node, kind, base_url, index)
        visual_blocks.append({"id": f"visual-{index + 1}", "type": kind, **props, "position": index})

    if "header" not in sections:
        sections.insert(0, "header")
    if "footer" not in sections:
        sections.append("footer")

    colors = Counter()
    fonts = Counter()
    for style in soup.find_all(style=True):
        value = str(style.get("style", "")).lower()
        for part in value.replace(";", " ").split():
            if ":" not in part:
                continue
            key, raw = part.split(":", 1)
            raw = raw.strip()
            if key.strip() in {"color", "background", "background-color"} and raw.startswith(("#", "rgb")):
                colors[raw] += 1
            if key.strip() == "font-family":
                fonts[raw] += 1

    palette = [color for color, _ in colors.most_common(5)]
    return {
        "sections": sections,
        "visual_blocks": visual_blocks,
        "design_system": {
            "colors": {
                "primary": palette[0] if palette else "#1a1a2e",
                "secondary": palette[1] if len(palette) > 1 else "#16213e",
                "accent": palette[2] if len(palette) > 2 else "#e94560",
                "background": "#ffffff",
                "text": "#333333",
            },
            "fonts": {
                "heading": fonts.most_common(1)[0][0] if fonts else "'Inter', sans-serif",
                "body": fonts.most_common(1)[0][0] if fonts else "'Inter', sans-serif",
            },
            "borderRadius": "8px",
        },
    }
