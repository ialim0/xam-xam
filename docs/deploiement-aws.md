# Déployer le bot WhatsApp sur AWS (ECS Express Mode)

Le bot tourne sur **Amazon ECS Express Mode** : AWS exécute l'image Docker sur Fargate et
fournit une **URL HTTPS** (`https://<identifiant>.ecs.<région>.on.aws`, affichée par `deploy.sh`). Aucun nom de domaine
ni serveur à administrer.

```
Meta ──► https://xa-….ecs.eu-west-3.on.aws/webhook ──► équilibreur (TLS) ──► tâche Fargate (1)
                                                                   ▲
                           SSM Parameter Store /xamxam/* ──────────┘ variables d'environnement
```

## Choix imposés par le code

| Le code… | donc… |
| --- | --- |
| répond au webhook puis traite le message en tâche de fond | Fargate convient : le CPU reste alloué hors requête (pas de Lambda). |
| garde la conversation, les rafales et les médias Meta en RAM | **une seule tâche** : `minTaskCount = maxTaskCount = 1`. |
| écrit le cache TTS et `bot-state.sqlite3` dans `/cache` | ce disque est éphémère : quotas, dédoublonnage et cache TTS repartent de zéro à chaque déploiement (sans gravité). |
| lit sa configuration dans l'environnement | chaque paramètre SSM devient une variable d'environnement. |

Coût indicatif (Paris) : environ 40 $/mois de Fargate (1 vCPU, 2 Gio en continu) et 16 à
20 $/mois d'équilibreur de charge, plus les journaux CloudWatch.

## Prérequis

- **AWS CLI v2** récente (avec les commandes `ecs create-express-gateway-service`),
  authentifiée (`aws configure` ou `aws sso login`) ; **Docker** ; `git` et `python3`.
- Votre utilisateur doit pouvoir gérer ECR, ECS, IAM (rôles `xamxam-*`), SSM `/xamxam/*`
  et lancer ECS Express Mode.

Région par défaut : `eu-west-3` (Paris), la plus proche du Sénégal. Pour une autre région :
`export AWS_REGION=...` avant chaque script.

## 1. Les secrets et la configuration

Tout va dans **SSM Parameter Store**, sous `/xamxam/<NOM_DE_LA_VARIABLE>`. Les secrets sont
des **SecureString** (chiffrés, gratuits) ; rien n'est écrit dans l'image ni dans le dépôt.

```bash
deploy/aws/set-secrets.sh
```

Le script demande chaque valeur (saisie masquée pour les secrets) ; entrée vide = inchangé.

| Type | Variables |
| --- | --- |
| SecureString | `WHATSAPP_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `RODIUM_API_KEY` (ou `GEMINI_API_KEY`), `KVICC_API_KEY`, `TIMALENS_API_KEY`, `LOG_HASH_KEY` (`openssl rand -hex 32`), `UNLIMITED_NUMBERS` |
| String | `WHATSAPP_PHONE_NUMBER_ID`, `LLM_PROVIDER` (`gemini` ou `rodium`), `KVICC_TTS_URL`, `KVICC_STT_URL`, `TIMALENS_VOICE`, `TIMALENS_MAX_CREDITS`, `RODIUM_MODEL`, `RODIUM_FALLBACK_MODEL` |

Tout autre réglage (`XAMXAM_REPLY_MODE`, `XAMXAM_VIDEOS_PER_DAY`…) s'ajoute de la même façon :

```bash
aws ssm put-parameter --name /xamxam/XAMXAM_VIDEOS_PER_DAY --type String --value 3 --overwrite
```

Le rôle d'exécution des tâches (`xamxam-execution`) n'a le droit de lire que `/xamxam/*`.
Une valeur modifiée n'est prise en compte qu'au prochain `deploy.sh`.

## 2. Déployer

```bash
deploy/aws/deploy.sh
```

Le script refuse un dépôt avec des modifications non commitées : l'image porte le hash du
commit. Il crée au besoin le dépôt ECR, le cluster et les rôles `xamxam-execution` et
`xamxam-infrastructure`, construit et pousse l'image, crée le service (ou le met à jour en
déploiement progressif), attend qu'il soit stable et affiche :

```
Santé : https://xa-….ecs.eu-west-3.on.aws/health
Webhook à saisir chez Meta : https://xa-….ecs.eu-west-3.on.aws/webhook
```

Le premier déploiement prend quelques minutes (équilibreur de charge, certificat).
Vérifiez `/health` : `"bot_ready": true` et `"missing_variables": []`.

## 3. Brancher Meta

Console Meta › WhatsApp › Configuration › Webhook :
- **URL de rappel** : l'URL `…/webhook` affichée ;
- **Jeton de vérification** : la valeur de `WHATSAPP_VERIFY_TOKEN` ;
- abonnez le champ **messages**.

## Exploitation

- **Nouvelle version** : commit, puis `deploy/aws/deploy.sh`.
- **Journaux** : console ECS › cluster `default` › service `xamxam` › Journaux (CloudWatch).
- **Arrêt** : pendant un déploiement, l'ancienne tâche reçoit SIGTERM et termine les réponses
  en cours (`drain`) ; ECS l'arrête de force après 30 s.
- **Suppression** : `aws ecs delete-express-gateway-service --service-arn <arn>` supprime le
  service et l'équilibreur qu'il a créé ; le dépôt ECR, les rôles et les paramètres restent.
