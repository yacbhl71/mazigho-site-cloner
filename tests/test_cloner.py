from app.cloner.analyzer import analyze
from app.cloner.rebuilder import _classify_page, rebuild, recommend_theme
from app.models import CloneRequest, JobStatus
from app.platforms.woocommerce import WooCommerceExtractor
from app.cloner.detector import detect, FORCED_WARNING, ROBOTS_BLOCKED_ERROR
from app.assets.uploader import AssetUploader
from app.assets.downloader import download_and_optimize
from app.config import Settings
from unittest.mock import patch
import httpx
import pytest

def test_analyzer_detects_sections():
    result = analyze('<header>Menu</header><section class="hero">Hero</section><div class="product-grid">x</div><footer>Footer</footer>')
    assert 'header' in result['sections'] and 'hero' in result['sections'] and 'product-grid' in result['sections'] and 'footer' in result['sections']


def test_analyzer_exports_rich_rendered_visual_props_in_order():
    html = '''<section class="hero"><h1>Real food</h1><p>Balanced energy</p><img src="//cdn.example.test/hero.jpg" alt="Hero"><a href="/shop">SHOP NOW</a></section>
    <section class="reviews"><h2>Reviews</h2><p>★★★★★ Great bar</p></section>'''
    result = analyze(html, 'https://shop.example.test/')
    project = rebuild('operator-yacbhl71', 'Demo', 'https://shop.example.test/', 'shopify', {'products': [], 'pages': [], 'navigation': []}, result, {})
    blocks = project['pages']['home']['blocks']
    assert blocks[0]['type'] == 'hero'
    assert blocks[0]['props']['imageUrl'] == 'https://cdn.example.test/hero.jpg'
    assert blocks[0]['props']['buttonLabel'] == 'SHOP NOW'
    assert any(block['type'] == 'testimonials' for block in blocks)


def test_rebuilder_never_includes_payment_data():
    project = rebuild('u1','Demo','https://shop.test','shopify',{'products':[{'title':'A','price':10,'images':[]}],'navigation':[]},{'sections':['header']},{})
    assert project['catalog'][0]['price'] == 10
    assert 'payment' not in str(project).lower() and 'checkout' not in str(project).lower()


def test_rebuilder_recommends_reusable_theme_without_forcing_it():
    recommendation = recommend_theme({"products": [{"title": "Blazer et robe en maille"}]}, {"visual_blocks": []})
    assert recommendation["themeId"] == "fashion"
    assert recommendation["confidence"] == "high"
    project = rebuild("u1", "Demo", "https://shop.test", "generic", {"products": [{"title": "Blazer", "price": 89, "currency": "CHF", "images": []}], "navigation": []}, {"sections": ["hero"]}, {})
    assert project["settings"]["recommendedTheme"]["themeId"] == "fashion"

def test_rebuilder_strips_shopify_variant_metadata_and_nulls():
    project = rebuild('u1', 'Demo', 'https://shop.test', 'shopify', {
        'products': [{'title': 'A', 'images': [], 'options': [{'name': 'Size'}], 'variants': [{
            'title': 'Standard', 'sku': None, 'option1': 'M', 'admin_graphql_api_id': 'gid://shopify/ProductVariant/1',
        }]}], 'navigation': []
    }, {'sections': ['header']}, {})
    variant = project['catalog'][0]['variants'][0]
    assert variant['options'] == {'Size': 'M'}
    assert 'sku' not in variant
    assert 'admin_graphql_api_id' not in variant

def test_request_rejects_non_http():
    try: CloneRequest(url='javascript:alert(1)', mazigho_user_id='u')
    except Exception: return
    assert False

@pytest.mark.asyncio
async def test_woocommerce_uses_domain_origin_for_public_api():
    class Response:
        status_code = 200
        def json(self):
            return [{"name": "Demo", "prices": {"price": "1250", "currency_minor_unit": 2}, "images": [], "categories": []}]
    class Client:
        async def get(self, url):
            assert "/a-propos/" not in url
            if "wc/store/v1/products" in url: return Response()
            return type("PagesResponse", (), {"status_code": 200, "json": lambda self: []})()
    result = await WooCommerceExtractor("https://shop.test/a-propos/", Client()).extract()
    assert result["products"][0]["name"] == "Demo"
    assert result["products"][0]["price"] == 12.5

def test_cms_page_classification_uses_multi_signal_archive_rule():
    assert _classify_page("about-us", "About us", "short") == "essentielle"
    assert _classify_page("ambassador-2021", "Ambassador", "") == "archivée"
    assert _classify_page("our-story", "Our story", "A useful page with enough content") == "à vérifier"

def test_rebuilder_creates_individual_sanitized_cms_pages():
    project = rebuild("u1", "Demo", "https://shop.test/", "shopify", {
        "products": [],
        "pages": [
            {"title": "Contact", "handle": "contact", "body_html": "<p>Contact</p><script>alert(1)</script>"},
            {"title": "Ambassador 2021", "handle": "ambassador-2021", "body_html": "<p></p>"},
            {"title": "Our story", "handle": "our-story", "body_html": "<p>Useful editorial content for review.</p>"},
        ],
        "navigation": [],
    }, {"sections": ["hero"]}, {})
    assert set(project["pages"]) == {"home", "contact", "ambassador-2021", "our-story"}
    assert project["pages"]["contact"]["category"] == "essentielle"
    assert project["pages"]["ambassador-2021"]["category"] == "archivée"
    assert project["pages"]["our-story"]["category"] == "à vérifier"
    assert "script" not in str(project["pages"]["contact"]).lower()

@pytest.mark.asyncio
async def test_robots_blocks_generic_site_unless_forced():
    class Response:
        status_code = 200
        url = "https://example.test/shop"
        text = "<html><body>Generic shop</body></html>"
        def raise_for_status(self): return None
    class RobotsResponse:
        status_code = 200
        text = "User-agent: *\nDisallow: /"
    class Client:
        async def get(self, url, **kwargs):
            return Response() if url.startswith("https://example.test/shop") else RobotsResponse()
    with pytest.raises(PermissionError, match="Ce site interdit"):
        await detect("https://example.test/shop", Client())
    result = await detect("https://example.test/shop", Client(), force=True)
    assert result.robots_status == "blocked"
    assert result.robots_warning == FORCED_WARNING

@pytest.mark.asyncio
async def test_inaccessible_robots_allows_with_warning():
    class Response:
        status_code = 200
        url = "https://example.test/"
        text = "<html><body>Shop</body></html>"
        def raise_for_status(self): return None
    class RobotsResponse:
        status_code = 404
        text = ""
    class Client:
        async def get(self, url, **kwargs):
            return Response() if url == "https://example.test/" else RobotsResponse()
    result = await detect("https://example.test/", Client())
    assert result.robots_status == "inaccessible"
    assert "non accessible" in (result.robots_warning or "")

def test_s3_uploader_builds_store_scoped_cdn_url():
    class FakeS3:
        def __init__(self): self.calls = []
        def put_object(self, **kwargs): self.calls.append(kwargs)
    fake = FakeS3()
    with patch('app.assets.uploader.boto3.client', return_value=fake):
        settings = Settings(aws_region='eu-west-1', aws_access_key_id='key', aws_secret_access_key='secret', s3_bucket='mazigho-assets', s3_prefix='cloned/', public_cdn_url='https://cdn.example.test')
        url = AssetUploader(settings, 'job', store_id='42').put(b'image', 'https://source.test/a.jpg', 'image/webp', 'webp')
    assert url.startswith('https://cdn.example.test/cloned/42/')
    assert fake.calls[0]['Key'].startswith('cloned/42/')
    assert fake.calls[0]['ContentType'] == 'image/webp'

def test_vercel_blob_uploader_has_priority_over_s3(monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self): return {'url': 'https://abc.public.blob.vercel-storage.com/cloned/42/image.webp'}
    monkeypatch.setenv('BLOB_READ_WRITE_TOKEN', 'blob-token-for-test')
    with patch('app.assets.uploader.httpx.put', return_value=Response()) as put:
        settings = Settings(aws_region='eu-west-1', aws_access_key_id='key', aws_secret_access_key='secret', s3_bucket='should-not-be-used', s3_prefix='cloned/')
        url = AssetUploader(settings, 'job', store_id='42').put(b'image', 'https://source.test/a.jpg', 'image/webp', 'webp')
    assert url.startswith('https://abc.public.blob.vercel-storage.com/')
    put.assert_called_once()
    assert put.call_args.kwargs['headers']['Authorization'] == 'Bearer blob-token-for-test'
    assert put.call_args.args[0].startswith('https://blob.vercel-storage.com/cloned/42/')

@pytest.mark.asyncio
async def test_image_download_retries_after_read_timeout():
    class Response:
        headers = {'content-type': 'image/png'}
        content = b'png-bytes'
        def raise_for_status(self): return None

    class Client:
        def __init__(self): self.calls = 0
        async def get(self, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ReadTimeout('temporary timeout')
            return Response()

    client = Client()
    asset = await download_and_optimize('https://source.test/image.png', client, retries=2)
    assert asset is not None
    assert client.calls == 2
