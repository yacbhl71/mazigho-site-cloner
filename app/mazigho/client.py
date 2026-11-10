import httpx
import asyncio
from app.config import Settings

class MazighoClient:
    def __init__(self, settings: Settings): self.settings = settings
    async def import_project(self, project: dict) -> dict:
        if not self.settings.mazigho_api_url or not self.settings.mazigho_api_key:
            return {'project_url': None, 'project_id': None, 'raw': {'mode': 'dry-run', 'message': 'MAZIGHO_API_URL/MAZIGHO_API_KEY non configurés'}}
        url = self.settings.mazigho_api_url.rstrip('/') + '/import/clone'
        headers = {'x-cloner-api-key': self.settings.mazigho_api_key, 'Content-Type': 'application/json'}
        timeout_seconds = float(getattr(self.settings, 'mazigho_import_timeout_seconds', 120.0))
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=min(20.0, timeout_seconds))) as client:
            for attempt in range(3):
                try:
                    response = await client.post(url, json=project, headers=headers)
                    if response.is_error:
                        raise RuntimeError(f"MAZIGHO import HTTP {response.status_code}: {response.text[:1000]}")
                    data = response.json()
                    break
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                    if attempt == 2:
                        raise RuntimeError('Délai dépassé pendant l’envoi du projet vers MAZIGHO.') from exc
                    await asyncio.sleep(1.5 * (attempt + 1))
        return {'project_url': data.get('project_url') or data.get('editor_url'), 'project_id': data.get('project_id'), 'summary': data.get('import_summary') or {}, 'raw': data}
