# MAZIGHO Site Cloner

Microservice autonome Python 3.12 / FastAPI / Playwright pour importer la structure et le catalogue public d’une boutique dans MAZIGHO. Il est séparé de l’application principale et ne clone jamais les paiements, clients ou commandes.

## Démarrage local

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8000
```

Ou avec Docker :

```bash
cp .env.example .env
docker compose up --build
```

Ouvrir `http://localhost:8000`. `POST /clone` lance un job et `GET /clone/{job_id}` renvoie son état. Le rate limit est de 5 jobs/minute/IP ; trois jobs peuvent s’exécuter en parallèle. Le timeout est de cinq minutes. Si `CLONER_API_KEY` est renseignée, `POST /clone` exige le header `X-Cloner-Api-Key` correspondant.

## Configuration MAZIGHO

Pour l’envoi réel, `MAZIGHO_API_URL` et `MAZIGHO_API_KEY` doivent pointer vers l’endpoint MAZIGHO sécurisé. Le proxy Studio transmet `X-Cloner-Api-Key` au microservice lorsque `CLONER_API_KEY` est configurée. Les boutiques importées restent privées et en statut `setup`.

## Stockage des images

Le cloner utilise en priorité Vercel Blob lorsque `BLOB_READ_WRITE_TOKEN` est défini. Il envoie alors les objets par PUT vers `blob.vercel-storage.com`, avec le chemin `cloned/...`. À défaut, il accepte un bucket S3 ou compatible S3 via `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_PREFIX`, `S3_ENDPOINT_URL` et `PUBLIC_CDN_URL`. Sans Blob ni S3, il utilise le stockage local de test. Les JPEG et PNG opaques sont convertis en WebP jusqu’à 1600 px, une miniature de 400 px est produite lorsque nécessaire, les SVG, GIF et PNG transparents sont conservés, et les fichiers de moins de 100 Ko ne sont pas recompressés.

L’audit du dépôt MAZIGHO a montré que son stockage actuel est principalement Vercel Blob, avec un ancien proxy Manus en secours, et non un bucket AWS S3 configuré. Les credentials S3 ne sont donc pas inventés. L’activation production nécessite une décision d’architecture et la validation du bucket/CDN. Voir `DEPLOYMENT.md`.

## Robots.txt et autorisation

Le clonage est bloqué par défaut lorsqu’un site interdit le chemin demandé dans `robots.txt`. Le job retourne un message expliquant que le site interdit le clonage automatique. `force=true` n’autorise la poursuite qu’après confirmation explicite de l’opérateur ; le warning juridique et le statut robots sont conservés dans le job et les métadonnées d’import. Un `robots.txt` inaccessible autorise la poursuite avec avertissement. Les APIs JSON publiques Shopify restent traitées comme des APIs et ne sont pas bloquées par une interdiction du storefront HTML.

Les conditions complètes sont dans `memory/CLONING_TERMS.md` et dans le dépôt MAZIGHO sous `memory/CLONING_TERMS.md`.

## Tests

```bash
python3 -m compileall -q app tests
pytest -q
npm run check # depuis le dépôt MAZIGHO
```

## Préparation production

`Dockerfile` utilise Python 3.12 slim et installe Chromium uniquement. `docker-compose.yml` définit le port 8000, le healthcheck et une limite recommandée de 2 Go RAM / 2 CPU. `PREDEPLOY_CHECKLIST.md` contient la recette manuelle à effectuer avant mise en production. Aucun déploiement n’est lancé automatiquement.
