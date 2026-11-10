from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx

FORCED_WARNING = ('Clonage forcé malgré l’interdiction robots.txt. '
                  'L’opérateur a confirmé être le propriétaire ou avoir l’autorisation.')
ROBOTS_BLOCKED_ERROR = ('Ce site interdit le clonage dans son robots.txt. '
                        'Si vous êtes le propriétaire, utilisez l’option force.')

@dataclass
class Detection:
    platform: str
    html: str
    final_url: str
    robots_warning: str | None = None
    robots_status: str = 'unknown'
    robots_blocked: bool = False
    api_exempt: bool = False


def _detect_platform(html: str) -> str:
    lower = html.lower()
    if 'cdn.shopify.com' in lower or 'window.shopify' in lower or '.myshopify.com' in lower:
        return 'shopify'
    if 'woocommerce' in lower or '/wp-content/plugins/woocommerce' in lower:
        return 'woocommerce'
    if 'prestashop' in lower:
        return 'prestashop'
    if 'bigcommerce' in lower:
        return 'bigcommerce'
    return 'generic'


async def _check_robots(final_url: str, platform: str, client: httpx.AsyncClient) -> tuple[str, str | None, bool, bool]:
    parsed = urlparse(final_url)
    robots_url = f'{parsed.scheme}://{parsed.netloc}/robots.txt'
    try:
        robots = await client.get(robots_url, follow_redirects=True)
    except (httpx.HTTPError, TimeoutError):
        return 'inaccessible', 'robots.txt non accessible ; le clonage est autorisé avec avertissement.', False, False
    if robots.status_code >= 400:
        return 'inaccessible', f'robots.txt non accessible (HTTP {robots.status_code}) ; le clonage est autorisé avec avertissement.', False, False
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(robots.text.splitlines())
    blocked = not parser.can_fetch('MAZIGHO-Site-Cloner/1.0', final_url)
    if not blocked:
        return 'allowed', None, False, False
    # Shopify public JSON endpoints are API reads, not HTML scraping. They
    # remain available even when the storefront path is disallowed.
    api_exempt = platform == 'shopify'
    warning = 'robots.txt interdit le chemin storefront ; les APIs Shopify publiques restent autorisées.' if api_exempt else ROBOTS_BLOCKED_ERROR
    return 'blocked', warning, True, api_exempt


async def detect(url: str, client: httpx.AsyncClient, force: bool = False) -> Detection:
    response = await client.get(url, follow_redirects=True)
    response.raise_for_status()
    html = response.text
    platform = _detect_platform(html)
    status, warning, blocked, api_exempt = await _check_robots(str(response.url), platform, client)
    if blocked and not force and not api_exempt:
        raise PermissionError(ROBOTS_BLOCKED_ERROR)
    if blocked and force:
        warning = FORCED_WARNING
    return Detection(platform, html, str(response.url), warning, status, blocked, api_exempt)
