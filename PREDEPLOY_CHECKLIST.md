# Checklist pré-déploiement MAZIGHO Site Cloner

## Sécurité et gouvernance

- [ ] Base de données de production sauvegardée.
- [ ] Clé API générée et configurée des deux côtés.
- [ ] Secrets stockés dans un gestionnaire sécurisé, jamais dans Git.
- [ ] CGU de clonage relues et publiées sur le site public.
- [ ] Confirmation propriétaire/autorisation visible dans le Studio.
- [ ] Blocage robots.txt testé par défaut.
- [ ] Mode force réservé à une confirmation explicite et journalisée.

## Stockage et images

- [ ] Bucket S3/S3-compatible provisionné et validé.
- [ ] Région, endpoint, bucket et CDN confirmés avec MAZIGHO.
- [ ] Politique d'écriture limitée au préfixe `cloned/`.
- [ ] Lecture publique via CDN testée avec une image non sensible.
- [ ] Images JPEG/PNG optimisées à 1600px maximum.
- [ ] Miniatures 400px vérifiées.
- [ ] SVG, PNG transparents et GIF animés conservés.
- [ ] Images de moins de 100 Ko non recompressées.

## Infrastructure

- [ ] VPS provisionné avec Docker.
- [ ] Minimum recommandé : 4 Go RAM ; limites conteneur : 2 Go / 2 CPU.
- [ ] DNS `cloner.mazigho.ch` configuré.
- [ ] SSL configuré et renouvellement automatique vérifié.
- [ ] Port 8000 non exposé publiquement sans reverse proxy.
- [ ] Health check répondant.
- [ ] Redémarrage automatique testé.

## Recette fonctionnelle

- [ ] Test end-to-end sur un site public autorisé.
- [ ] Import Shopify vérifié.
- [ ] Import WooCommerce vérifié.
- [ ] Site interdisant tout dans robots.txt bloqué.
- [ ] `force=true` accepté uniquement avec avertissement.
- [ ] robots.txt inaccessible autorisé avec warning.
- [ ] Images accessibles depuis le CDN.
- [ ] Boutique MAZIGHO créée en `setup` et privée.
- [ ] Aucun paiement, client ou commande importé.

## Exploitation

- [ ] Monitoring et alertes en place.
- [ ] Logs sans secrets ni données personnelles inutiles.
- [ ] Procédure de mise à jour testée.
- [ ] Rollback planifié et image précédente conservée.
