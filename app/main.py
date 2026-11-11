import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.cloner.pipeline import Pipeline
from app.config import get_settings
from app.models import CloneRequest, CloneResponse, JobState, JobStatus

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ASSETS = Path('/tmp/mazigho-cloner-assets')
LOCAL_ASSETS.mkdir(parents=True, exist_ok=True)
EXPORTS = Path('/tmp/mazigho-cloner-exports')
EXPORTS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='MAZIGHO Site Cloner', version='1.0.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
app.mount('/local-assets', StaticFiles(directory=LOCAL_ASSETS), name='local-assets')
settings = get_settings()
runtime_ui_password = settings.cloner_ui_password
jobs: dict[UUID, JobState] = {}
tasks: dict[UUID, asyncio.Task] = {}
requests_by_ip: dict[str, deque[datetime]] = defaultdict(deque)
semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
UI_COOKIE = 'mazigho_cloner_session'


def allow(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    q = requests_by_ip[ip]
    while q and q[0] < now - timedelta(minutes=1):
        q.popleft()
    if len(q) >= 5:
        return False
    q.append(now)
    return True


def ui_auth_configured() -> bool:
    return bool(settings.cloner_ui_username and runtime_ui_password and settings.cloner_ui_session_secret)


def make_session(username: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({'u': username, 'exp': int(time.time()) + 8 * 3600}, separators=(',', ':')).encode()).decode().rstrip('=')
    signature = hmac.new(settings.cloner_ui_session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def valid_session(request: Request) -> bool:
    if not ui_auth_configured():
        return False
    token = request.cookies.get(UI_COOKIE, '')
    try:
        payload, signature = token.split('.', 1)
        expected = hmac.new(settings.cloner_ui_session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        padded = payload + '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return data.get('u') == settings.cloner_ui_username and int(data.get('exp', 0)) > int(time.time())
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def valid_server_key(request: Request) -> bool:
    return bool(settings.cloner_api_key) and secrets.compare_digest(request.headers.get('x-cloner-api-key', ''), settings.cloner_api_key)


def require_ui_or_server(request: Request) -> None:
    if not valid_session(request) and not valid_server_key(request):
        raise HTTPException(401, 'Authentification requise.')


@app.get('/', include_in_schema=False)
async def home(request: Request):
    if not ui_auth_configured():
        return JSONResponse({'status': 'misconfigured', 'message': 'Configurez CLONER_UI_USERNAME, CLONER_UI_PASSWORD et CLONER_UI_SESSION_SECRET.'}, status_code=503)
    if not valid_session(request):
        return RedirectResponse('/login', status_code=303)
    return FileResponse(ROOT / 'templates' / 'index.html')


@app.get('/login', include_in_schema=False)
async def login_page(request: Request):
    if valid_session(request):
        return RedirectResponse('/', status_code=303)
    return FileResponse(ROOT / 'templates' / 'login.html')


@app.post('/auth/login', include_in_schema=False)
async def login(request: Request):
    if not ui_auth_configured():
        raise HTTPException(503, 'La connexion du cloner n’est pas encore configurée côté serveur.')
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, 'Requête de connexion invalide.')
    username = str(body.get('username', ''))
    password = str(body.get('password', ''))
    if not hmac.compare_digest(username, settings.cloner_ui_username) or not hmac.compare_digest(password, runtime_ui_password):
        raise HTTPException(401, 'Identifiants invalides.')
    response = JSONResponse({'ok': True})
    response.set_cookie(UI_COOKIE, make_session(username), httponly=True, secure=True, samesite='lax', max_age=8 * 3600, path='/')
    return response


@app.post('/auth/reset', include_in_schema=False)
async def reset_password(request: Request):
    global runtime_ui_password
    if not settings.cloner_ui_recovery_code:
        raise HTTPException(503, 'La récupération n’est pas configurée côté serveur.')
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, 'Requête de récupération invalide.')
    username = str(body.get('username', ''))
    recovery_code = str(body.get('recovery_code', ''))
    new_password = str(body.get('new_password', ''))
    if not hmac.compare_digest(username, settings.cloner_ui_username) or not hmac.compare_digest(recovery_code, settings.cloner_ui_recovery_code):
        raise HTTPException(401, 'Code de récupération invalide.')
    if len(new_password) < 10:
        raise HTTPException(400, 'Le nouveau mot de passe doit contenir au moins 10 caractères.')
    runtime_ui_password = new_password
    response = JSONResponse({'ok': True, 'message': 'Mot de passe réinitialisé. Utilisez-le pour vous reconnecter.'})
    response.delete_cookie(UI_COOKIE, path='/')
    return response


@app.post('/auth/logout', include_in_schema=False)
async def logout():
    response = JSONResponse({'ok': True})
    response.delete_cookie(UI_COOKIE, path='/')
    return response


@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'mazigho-site-cloner', 'jobs': len(jobs), 'ui_auth_configured': ui_auth_configured()}


async def execute(job_id: UUID, payload: CloneRequest):
    async with semaphore:
        state = jobs[job_id]
        try:
            await asyncio.wait_for(Pipeline(settings, state).run(str(payload.url), payload.mazigho_user_id, payload.mazigho_project_name, payload.force, payload.shopify_password), timeout=settings.max_clone_duration_seconds)
        except asyncio.TimeoutError:
            state.status, state.progress, state.error, state.message = JobStatus.FAILED, 100, f'Durée maximale dépassée ({settings.max_clone_duration_seconds}s)', 'Le clonage a dépassé le délai maximal.'
        except Exception as exc:
            state.status, state.progress, state.error, state.message = JobStatus.FAILED, 100, str(exc)[:500], 'Le clonage a échoué.'


@app.post('/clone', response_model=CloneResponse, status_code=202)
async def create_clone(payload: CloneRequest, request: Request, background_tasks: BackgroundTasks):
    require_ui_or_server(request)
    ip = request.client.host if request.client else 'unknown'
    if not allow(ip):
        raise HTTPException(429, 'Limite atteinte : maximum 5 clonages par minute et par adresse IP.')
    job_id = uuid4()
    jobs[job_id] = JobState(job_id=job_id, status=JobStatus.QUEUED, progress=0, message='En file d’attente…')
    tasks[job_id] = asyncio.create_task(execute(job_id, payload))
    return CloneResponse(job_id=job_id, status=JobStatus.QUEUED)


@app.get('/clone/{job_id}', response_model=JobState)
async def get_clone(job_id: UUID, request: Request):
    require_ui_or_server(request)
    state = jobs.get(job_id)
    if not state:
        raise HTTPException(404, 'Job introuvable')
    return state


@app.get('/clone/{job_id}/export', include_in_schema=False)
async def download_clone_export(job_id: UUID, request: Request):
    require_ui_or_server(request)
    path = EXPORTS / f'{job_id}.json'
    if not path.is_file():
        raise HTTPException(404, 'Export introuvable ou expiré.')
    return FileResponse(path, media_type='application/json', filename=f'mazigho-clone-{job_id}.json')
