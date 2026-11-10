from collections import Counter
from typing import Any
from bs4 import BeautifulSoup

SECTION_RULES = {
    'header': ('header', 'nav', 'menu'), 'hero': ('hero', 'banner', 'masthead'),
    'product-grid': ('product', 'collection', 'catalog'), 'testimonials': ('testimonial', 'review'),
    'cta': ('cta', 'call-to-action'), 'about': ('about', 'story'), 'newsletter': ('newsletter', 'subscribe'),
    'footer': ('footer',),
}

def analyze(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, 'lxml')
    sections: list[str] = []
    for node in soup.find_all(['header', 'main', 'section', 'footer', 'nav', 'div']):
        marker = f"{node.name} {node.get('id','')} {' '.join(node.get('class', []))}".lower()
        for kind, tokens in SECTION_RULES.items():
            if any(token in marker for token in tokens) and kind not in sections:
                sections.append(kind)
    if 'header' not in sections: sections.insert(0, 'header')
    if 'footer' not in sections: sections.append('footer')
    colors = Counter()
    fonts = Counter()
    for style in soup.find_all(style=True):
        text = style.get('style', '').lower()
        for part in text.replace(';', ' ').split():
            if ':' in part:
                key, value = part.split(':', 1)
                if key.strip() in {'color', 'background', 'background-color'} and value.strip().startswith(('#', 'rgb')):
                    colors[value.strip()] += 1
                if key.strip() == 'font-family': fonts[value.strip()] += 1
    palette = [c for c, _ in colors.most_common(5)]
    return {
        'sections': sections,
        'design_system': {
            'colors': {'primary': palette[0] if palette else '#1a1a2e', 'secondary': palette[1] if len(palette)>1 else '#16213e', 'accent': palette[2] if len(palette)>2 else '#e94560', 'background': '#ffffff', 'text': '#333333'},
            'fonts': {'heading': fonts.most_common(1)[0][0] if fonts else "'Inter', sans-serif", 'body': fonts.most_common(1)[0][0] if fonts else "'Inter', sans-serif"},
            'borderRadius': '8px',
        },
    }
