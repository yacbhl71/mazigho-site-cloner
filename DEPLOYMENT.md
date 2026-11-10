# Déploiement du MAZIGHO Site Cloner

Ce document prépare un déploiement manuel. Aucun déploiement réel n'est exécuté par ce projet.

## Prérequis

- VPS Linux avec Docker et Docker Compose v2.
- 4 Go de RAM recommandés ; le conteneur est limité à 2 Go et 2 CPU.
- DNS administrable pour `cloner.mazigho.ch`.
- Bucket S3 ou compatible S3 avec accès privé d'écriture et lecture publique via CDN.
- URL et clé API du endpoint MAZIGHO `/api/import/clone`.
- Clé API distincte pour le service cloner, si une authentification réseau est activée devant le service.

## Configuration Vercel Blob ou S3

MAZIGHO utilise actuellement Vercel Blob pour ses médias applicatifs. Le cloner utilise Vercel Blob en priorité lorsqu'un `BLOB_READ_WRITE_TOKEN` est configuré. À défaut, il utilise un bucket S3/S3-compatible séparé ou validé explicitement par l'opérateur. Ne pas inventer de bucket, de CDN ou de credentials à partir du seul nom de domaine.

Renseigner dans `.env` :

```env
BLOB_READ_WRITE_TOKEN=...
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=...
S3_PREFIX=cloned/
S3_ENDPOINT_URL=
PUBLIC_CDN_URL=https://cdn.mazigho.ch
```

Avec Vercel Blob, l'URL publique renvoyée par l'API Blob est conservée telle quelle. Avec S3, l'URL utilise le CDN configuré s'il existe, sinon l'URL régionale standard du bucket.

Le préfixe attendu est `cloned/`. Les objets sont organisés par portée d'import et hash d'URL. Avant production, réserver l'identifiant de boutique MAZIGHO afin d'obtenir exactement `cloned/{store_id}/{filename}.webp` ; le mode local de préparation utilise une portée `pending-{job_id}` jusqu'à la création de la boutique.

## DNS et SSL

1. Créer `cloner.mazigho.ch` vers l'IP publique du VPS.
2. Terminer TLS avec Caddy, nginx + Let's Encrypt ou un équivalent.
3. Ne publier que HTTPS et limiter le port 8000 à l'écoute locale ou au reverse proxy.
4. Transmettre `X-Cloner-Api-Key` uniquement sur le réseau interne ou via le reverse proxy sécurisé.

## Lancement

```bash
cp .env.example .env
# renseigner manuellement les secrets et les URLs validées

docker compose build
docker compose up -d

docker compose ps
curl --fail https://cloner.mazigho.ch/health
```

## Vérification post-déploiement

- `GET /health` répond avec `status=ok`.
- Un site de test autorisé est cloné sans accès privé.
- Une URL interdite par robots.txt est bloquée par défaut.
- Le mode `force=true` produit l'avertissement juridique attendu.
- Les URLs d'images retournées par l'import pointent vers le CDN ou le bucket validé.
- Les données de paiement, clients et commandes ne sont jamais présentes dans le payload.

## Monitoring et logs

Surveiller :

```bash
docker compose logs -f --tail=200 cloner
docker stats
```

Alerter sur les statuts `failed`, les timeouts, les réponses S3 non-2xx, les erreurs MAZIGHO 4xx/5xx et les refus robots répétés. Ne pas journaliser de credentials ni de contenu client privé.

## Mise à jour

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d --remove-orphans
curl --fail https://cloner.mazigho.ch/health
```

Conserver l'image précédente et la dernière configuration `.env` dans un coffre sécurisé afin de permettre un rollback manuel.
