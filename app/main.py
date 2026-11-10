import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.cloner.pipeline import Pipeline
from app.config import get_settings
from app.models import CloneRequest, CloneResponse, JobState, JobStatus

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ASSETS = Path('/tmp/mazigho-cloner-assets')
LOCAL_ASSETS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='MAZIGHO Site Cloner', version='1.0.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
app.mount('/local-assets', StaticFiles(directory=LOCAL_ASSETS), name='local-assets')
settings = get_settings(); jobs: dict[UUID, JobState] = {}; tasks: dict[UUID, asyncio.Task] = {}; requests_by_ip: dict[str, deque[datetime]] = defaultdict(deque); semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

def allow(ip: str) -> bool:
    now = datetime.now(timezone.utc); q = requests_by_ip[ip]
    while q and q[0] < now - timedelta(minutes=1): q.popleft()
    if len(q) >= 5: return False
    q.append(now); return True

@app.get('/', include_in_schema=False)
async def home(): return FileResponse(ROOT / 'templates' / 'index.html')

@app.get('/health')
async def health(): return {'status': 'ok', 'service': 'mazigho-site-cloner', 'jobs': len(jobs)}

async def execute(job_id: UUID, payload: CloneRequest):
    async with semaphore:
        state = jobs[job_id]
        try:
            await asyncio.wait_for(Pipeline(settings, state).run(str(payload.url), payload.mazigho_user_id, payload.mazigho_project_name, payload.force), timeout=settings.max_clone_duration_seconds)
        except asyncio.TimeoutError:
            state.status, state.progress, state.error, state.message = JobStatus.FAILED, 100, f'Durée maximale dépassée ({settings.max_clone_duration_seconds}s)', 'Le clonage a dépassé le délai maximal.'
        except Exception as exc:
            state.status, state.progress, state.error, state.message = JobStatus.FAILED, 100, str(exc)[:500], 'Le clonage a échoué.'

@app.post('/clone', response_model=CloneResponse, status_code=202)
async def create_clone(payload: CloneRequest, request: Request, background_tasks: BackgroundTasks):
    if settings.cloner_api_key and request.headers.get('x-cloner-api-key') != settings.cloner_api_key:
        raise HTTPException(401, 'Clé API cloner invalide.')
    ip = request.client.host if request.client else 'unknown'
    if not allow(ip): raise HTTPException(429, 'Limite atteinte : maximum 5 clonages par minute et par adresse IP.')
    job_id = uuid4(); jobs[job_id] = JobState(job_id=job_id, status=JobStatus.QUEUED, progress=0, message='En file d’attente…')
    task = asyncio.create_task(execute(job_id, payload)); tasks[job_id] = task
    return CloneResponse(job_id=job_id, status=JobStatus.QUEUED)

@app.get('/clone/{job_id}', response_model=JobState)
async def get_clone(job_id: UUID):
    state = jobs.get(job_id)
    if not state: raise HTTPException(404, 'Job introuvable')
    return state
