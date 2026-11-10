import httpx
from app.config import Settings

class MazighoClient:
    def __init__(self, settings: Settings): self.settings = settings
    async def import_project(self, project: dict) -> dict:
        if not self.settings.mazigho_api_url or not self.settings.mazigho_api_key:
            return {'project_url': None, 'project_id': None, 'raw': {'mode': 'dry-run', 'message': 'MAZIGHO_API_URL/MAZIGHO_API_KEY non configurés'}}
        url = self.settings.mazigho_api_url.rstrip('/') + '/import/clone'
        headers = {'x-cloner-api-key': self.settings.mazigho_api_key, 'Content-Type': 'application/json'}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=project, headers=headers)
            if response.is_error:
                raise RuntimeError(f"MAZIGHO import HTTP {response.status_code}: {response.text[:1000]}")
            data = response.json()
        return {'project_url': data.get('project_url') or data.get('editor_url'), 'project_id': data.get('project_id'), 'summary': data.get('import_summary') or {}, 'raw': data}
