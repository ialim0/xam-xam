# Déploiement du bot WhatsApp Xam-Xam sur Google Cloud Run (alternative)

> **Le déploiement principal est désormais AWS (EC2, Docker Compose, Caddy) :
> voir [deploiement-aws.md](deploiement-aws.md).** Ce guide reste valable pour Cloud Run.

Deux étapes : tester en local avec ngrok, puis déployer sur Google Cloud Run.

## Prérequis

- Une application Meta avec le produit **WhatsApp** (API WhatsApp Cloud) : un numéro de test,
  son **Phone number ID**, un **jeton d'accès** et le **secret de l'application**
  (Paramètres de l'app → Général).
- Une clé **Gemini** et le nom du modèle à utiliser (`GEMINI_MODEL`, aucun modèle par défaut).
- La clé d'équipe **Kiriku** (`sk-kiriku-...`) et les URL des deux routes (voir `.env.example`).
- `ffmpeg` installé (`sudo apt install ffmpeg`, `brew install ffmpeg`…).

Variables à définir (voir `.env.example`) :

| Variable | Rôle |
| --- | --- |
| `WHATSAPP_TOKEN` | jeton d'accès de l'API Graph |
| `WHATSAPP_PHONE_NUMBER_ID` | identifiant du numéro qui envoie les réponses |
| `WHATSAPP_VERIFY_TOKEN` | chaîne de votre choix, recopiée dans la console Meta |
| `WHATSAPP_APP_SECRET` | vérifie la signature `X-Hub-Signature-256` des notifications |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | résolution des exercices |
| `KVICC_TTS_URL`, `KVICC_STT_URL`, `KVICC_API_KEY` | voix et transcription Kiriku |
| `LOG_HASH_KEY` | clé HMAC des identifiants dans les logs (`openssl rand -hex 32`) |
| `UNLIMITED_NUMBERS` | numéros sans limite (équipe, démos), séparés par des virgules |

`GET /health` indique si le bot est prêt et liste les variables manquantes (noms seulement).

## 1. En local avec ngrok

```bash
cp .env.example .env          # puis renseignez les valeurs
set -a; source .env; set +a
pip install -e ".[dev]"
uvicorn --factory xamxam.whatsapp.app:create_app --port 8000

# Dans un autre terminal : URL publique HTTPS vers le port 8000
ngrok http 8000
```

Dans la console Meta, **WhatsApp → Configuration → Webhook** :

1. URL de rappel : `https://<sous-domaine>.ngrok-free.app/webhook` ;
2. Jeton de vérification : la valeur de `WHATSAPP_VERIFY_TOKEN` ;
3. Validez (Meta appelle `GET /webhook` et attend le challenge), puis abonnez le champ
   **messages**.

Envoyez une photo d'exercice au numéro de test : l'accusé de réception arrive aussitôt, la
note vocale et la réponse finale quelques secondes plus tard. En local, les caches sont dans
`.cache/tts` et `.cache/stt`.

## 2. Sur Google Cloud Run

### Pourquoi ces options

| Option | Raison |
| --- | --- |
| `--max-instances=1` | la file d'attente Kiriku (30 requêtes/min, TTS + STT) et les limites par élève sont en mémoire : une seule instance garantit un quota vraiment global |
| `--min-instances=1` | pas de démarrage à froid, et la file en mémoire n'est pas perdue quand le trafic s'arrête |
| `--no-cpu-throttling` | le webhook répond 200 tout de suite et traite en tâche de fond : sans CPU alloué en permanence, ce traitement serait ralenti après la réponse |
| volume Cloud Storage sur `/cache` | les caches TTS et STT survivent aux redémarrages et aux redéploiements |

### Commandes

```bash
PROJECT=mon-projet
REGION=europe-west1            # région de niveau 1, proche du Sénégal
BUCKET=${PROJECT}-xamxam-cache
SERVICE=xamxam-bot

gcloud config set project $PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com

# Bucket des caches, et droit d'écriture pour le compte de service de Cloud Run
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
SA=$(gcloud projects describe $PROJECT --format='value(projectNumber)')-compute@developer.gserviceaccount.com
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
    --member=serviceAccount:$SA --role=roles/storage.objectAdmin

# Secrets : une entrée par variable sensible (la valeur est lue sur l'entrée standard)
for name in WHATSAPP_TOKEN WHATSAPP_VERIFY_TOKEN WHATSAPP_APP_SECRET GEMINI_API_KEY \
            KVICC_API_KEY LOG_HASH_KEY UNLIMITED_NUMBERS; do
  read -rsp "$name : " value; echo
  printf '%s' "$value" | gcloud secrets create $name --data-file=-
  gcloud secrets add-iam-policy-binding $name \
      --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
done

# Construction de l'image (Dockerfile du dépôt) et déploiement
gcloud run deploy $SERVICE \
    --source . \
    --region $REGION \
    --allow-unauthenticated \
    --execution-environment gen2 \
    --cpu 1 --memory 1Gi \
    --min-instances 1 --max-instances 1 \
    --no-cpu-throttling \
    --add-volume name=cache,type=cloud-storage,bucket=$BUCKET \
    --add-volume-mount volume=cache,mount-path=/cache \
    --set-env-vars XAMXAM_CACHE_DIR=/cache,GEMINI_MODEL=<modele>,WHATSAPP_PHONE_NUMBER_ID=<id>,KVICC_TTS_URL=<url-tts>,KVICC_STT_URL=<url-stt> \
    --set-secrets WHATSAPP_TOKEN=WHATSAPP_TOKEN:latest,WHATSAPP_VERIFY_TOKEN=WHATSAPP_VERIFY_TOKEN:latest,WHATSAPP_APP_SECRET=WHATSAPP_APP_SECRET:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,KVICC_API_KEY=KVICC_API_KEY:latest,LOG_HASH_KEY=LOG_HASH_KEY:latest,UNLIMITED_NUMBERS=UNLIMITED_NUMBERS:latest
```

`--allow-unauthenticated` est nécessaire : Meta appelle le webhook sans identifiants Google.
La sécurité repose sur la signature `X-Hub-Signature-256`, vérifiée à chaque notification.

Remplacez ensuite l'URL ngrok par `https://<service>-<hash>.<region>.run.app/webhook` dans la
console Meta. Vérifiez : `curl https://<url>/health` doit renvoyer `"bot_ready": true`.

### Coût estimé

Avec 1 instance allumée en permanence (1 vCPU, 1 Gio) et la facturation à l'instance, aux tarifs
du niveau 1 consultés en octobre 2026 (0,000018 $ par vCPU-seconde, 0,000002 $ par Gio-seconde,
gratuité mensuelle de 240 000 vCPU-secondes et 450 000 Gio-secondes) :

| Poste | Calcul (30 jours = 2 592 000 s) | Coût mensuel |
| --- | --- | --- |
| CPU | (2 592 000 − 240 000) × 0,000018 $ | ≈ 42,3 $ |
| Mémoire | (2 592 000 − 450 000) × 0,000002 $ | ≈ 4,3 $ |
| Cloud Storage (caches, < 1 Go) | stockage et opérations | < 0,10 $ |
| Secret Manager (7 secrets) | 0,06 $ par version active | ≈ 0,40 $ |
| **Total** | | **≈ 47 $ par mois** |

Ce total ne compte ni Gemini (facturé à l'usage), ni l'API WhatsApp, ni la sortie réseau.
Pour un événement ponctuel, on peut repasser à `--min-instances 0` entre deux démonstrations
(la file en mémoire est alors perdue à l'arrêt, mais pas les caches). Les tarifs évoluent :
vérifiez la [page de tarification Cloud Run](https://cloud.google.com/run/pricing).

## Confidentialité et exploitation

- Les médias reçus sont téléchargés dans un dossier temporaire, supprimé à la fin de chaque
  traitement. Les caches ne contiennent que des audios générés et des transcriptions,
  indexés par empreinte.
- Les logs ne contiennent ni numéro ni contenu : une ligne `job {...}` par demande, avec un
  identifiant haché (HMAC avec `LOG_HASH_KEY`), le résultat, la vérification, les durées par
  étape, le nombre de requêtes par service et le type d'erreur éventuel.
- L'API Kiriku du challenge reste disponible jusqu'au 16 octobre 2026.
