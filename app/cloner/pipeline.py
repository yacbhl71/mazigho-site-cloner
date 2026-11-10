import asyncio
from urllib.parse import urlparse
import httpx
from playwright.async_api import async_playwright
from app.assets.downloader import download_and_optimize
from app.assets.uploader import AssetUploader
from app.cloner.analyzer import analyze
from app.cloner.detector import detect, FORCED_WARNING
from app.cloner.rebuilder import rebuild
from app.config import Settings
from app.mazigho.client import MazighoClient
from app.models import JobState, JobStatus
from app.platforms.generic import GenericExtractor
from app.platforms.shopify import ShopifyExtractor
from app.platforms.woocommerce import WooCommerceExtractor

class Pipeline:
    def __init__(self, settings: Settings, state: JobState): self.settings, self.state = settings, state
    def update(self, status: JobStatus, progress: int, message: str):
        self.state.status, self.state.progress, self.state.message, self.state.updated_at = status, progress, message, __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    async def run(self, url: str, user_id: str, project_name: str | None, force: bool = False, shopify_password: str | None = None):
        try:
            timeout = httpx.Timeout(self.settings.request_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, headers={'User-Agent': self.settings.user_agent}) as client:
                self.update(JobStatus.DETECTING, 10, 'Détection de la plateforme…')
                detection = await detect(url, client, force=force)
                self.state.platform_detected = detection.platform
                self.state.robots_warning = detection.robots_warning
                self.state.robots_status = detection.robots_status
                self.state.force_confirmed = bool(force and detection.robots_blocked)
                if detection.robots_warning: self.state.warnings.append(detection.robots_warning)
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=True)
                    page = await browser.new_page(user_agent=self.settings.user_agent, viewport={'width': 1440, 'height': 1000})
                    try: await page.goto(detection.final_url, wait_until='domcontentloaded', timeout=int(self.settings.request_timeout_seconds*1000))
                    except Exception: pass
                    if detection.platform == 'shopify' and shopify_password:
                        password_input = page.locator('input[type="password"]').first
                        if await password_input.count():
                            await password_input.fill(shopify_password)
                            await password_input.press('Enter')
                            try: await page.wait_for_load_state('domcontentloaded', timeout=15000)
                            except Exception: pass
                            if await page.locator('input[type="password"]').count():
                                raise RuntimeError('Mot de passe Shopify refusé ou boutique toujours verrouillée.')
                            for cookie in await page.context.cookies():
                                client.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'), path=cookie.get('path', '/'))
                    self.update(JobStatus.EXTRACTING, 25, 'Extraction des produits et pages…')
                    extractor = {'shopify': ShopifyExtractor, 'woocommerce': WooCommerceExtractor}.get(detection.platform, GenericExtractor)(detection.final_url, client, page)
                    extracted = await extractor.extract()
                    self.state.products_count = len(extracted.get('products', []))
                    self.state.variants_count = sum(len(product.get('variants', []) or []) for product in extracted.get('products', []))
                    self.state.images_count = sum(len(product.get('images', []) or []) for product in extracted.get('products', []))
                    self.state.pages_count = len(extracted.get('pages', []))
                    self.update(JobStatus.ANALYZING, 45, 'Analyse du design et des sections…')
                    analysis = analyze(await page.content())
                    await browser.close()
                self.update(JobStatus.UPLOADING, 60, 'Optimisation et stockage des images…')
                # A newly imported store ID does not exist until MAZIGHO creates
                # the draft. Use a job-scoped prefix locally; production can pass
                # a reserved store ID through this same uploader contract.
                uploader, assets = AssetUploader(self.settings, str(self.state.job_id), store_id=f'pending-{self.state.job_id}'), {}
                image_urls = []
                for product in extracted.get('products', []):
                    for image in product.get('images', []) or []:
                        if isinstance(image, dict) and (u := (image.get('src') or image.get('url'))): image_urls.append(u)
                for index, original in enumerate(dict.fromkeys(image_urls)):
                    asset = await download_and_optimize(original, client, self.settings.image_max_width, self.settings.image_thumb_width, self.settings.image_unchanged_threshold_bytes)
                    if asset:
                        assets[original] = uploader.put(asset.content, original, asset.content_type, asset.extension)
                        if asset.thumbnail and asset.thumbnail_content_type:
                            assets[f'{original}#thumb'] = uploader.put(asset.thumbnail, original, asset.thumbnail_content_type, 'webp', thumbnail=True)
                    else: self.state.warnings.append(f'Image non téléchargée : {original}')
                    self.state.progress = min(85, 60 + int((index+1)/max(len(set(image_urls)),1)*25))
                project = rebuild(user_id, project_name or f'Import {urlparse(url).netloc}', url, detection.platform, extracted, analysis, assets)
                project['settings'].update({'robotsStatus': detection.robots_status, 'robotsForceConfirmed': self.state.force_confirmed})
                self.update(JobStatus.SENDING, 90, 'Envoi du projet vers MAZIGHO…')
                result = await MazighoClient(self.settings).import_project(project)
                self.state.mazigho_project_url = result.get('project_url') or result.get('editor_url')
                summary = result.get('summary') or result.get('import_summary') or {}
                self.state.warnings.extend(summary.get('warnings', []) if isinstance(summary.get('warnings', []), list) else [])
                self.update(JobStatus.COMPLETED, 100, 'Clonage terminé.' if self.state.mazigho_project_url else 'Clonage terminé en mode validation locale.')
        except asyncio.CancelledError: raise
        except Exception as exc:
            self.state.status, self.state.progress, self.state.error, self.state.message = JobStatus.FAILED, 100, str(exc)[:500], 'Le clonage a échoué.'
