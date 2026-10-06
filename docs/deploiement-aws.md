# Déploiement du bot WhatsApp Xam-Xam sur AWS

Cible : **une instance EC2** (t3.small, région eu-west-3 Paris) qui fait tourner le bot et
**Caddy** (HTTPS automatique) avec **Docker Compose**. Le cache des audios d'explication (TTS) vit sur un **volume EBS
chiffré** séparé du disque système, sauvegardé chaque jour dans un **bucket S3** privé.
Aucun port SSH : l'administration passe par **SSM Session Manager**, les déploiements par
**SSM Run Command**.

```
                 Internet (80, 443 uniquement)
                          │
   Meta ──► https://<domaine>/webhook ──► Caddy ──► bot:8080 ──► /cache (EBS chiffré)
                                                       ▲              │ timer quotidien
                       SSM Parameter Store /xamxam/ ───┘ (tmpfs)      ▼
                                                                   S3 (versionné)
   Poste de l'équipe : deploy.sh ──► ECR (image) + S3 (paquet) ──► SSM Run Command
```

Le code applicatif ne dépend pas d'AWS : il lit ses variables d'environnement et utilise
`/cache` comme un simple dossier.

## Prérequis

- Un compte AWS, et sur votre poste : **AWS CLI v2** authentifiée, **Terraform ≥ 1.6**,
  **Docker** avec `buildx`, et le [plugin Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
  pour ouvrir une session sur l'instance.
- Un nom de domaine dont vous gérez le DNS (ex. `bot.example.org`).
- Les valeurs listées à l'étape 3 (Meta, modèle de langage, Kiriku), et l'accès au modèle
  Bedrock choisi dans la région voulue (voir [modeles.md](modeles.md)).

Permissions de **votre** utilisateur (et non de l'instance) :

| Étape | Actions nécessaires |
| --- | --- |
| `terraform apply` | création d'EC2, EBS, Elastic IP, security group, S3, ECR, IAM (rôle et profil d'instance) |
| Paramètres | `ssm:PutParameter` sur `/xamxam/*` (`kms:Encrypt` via la clé `aws/ssm`) |
| `deploy.sh` | push ECR sur le dépôt `xamxam`, `s3:PutObject` sur `<bucket>/deploy/*`, `ssm:SendCommand` (instance + document `AWS-RunShellScript`), `ssm:GetCommandInvocation` |
| Administration | `ssm:StartSession` sur l'instance |

`ssm:SendCommand` n'appartient qu'à votre utilisateur : le rôle de l'instance ne l'a pas.

## 1. Créer l'infrastructure

```bash
cd deploy/aws/terraform
cp terraform.tfvars.example terraform.tfvars   # domaine, nom du bucket (unique au monde)
terraform init
terraform plan
terraform apply
terraform output                               # public_ip, instance_id, ecr_repository_url…
```

Ce qui est créé :

| Ressource | Détails |
| --- | --- |
| EC2 t3.small | Amazon Linux 2023, IMDSv2 obligatoire (1 saut : les conteneurs n'accèdent pas aux identifiants du rôle), disque système chiffré, crédits CPU « standard » |
| Elastic IP | adresse fixe pour l'enregistrement DNS |
| Security group | entrée TCP 80 et 443 uniquement (IPv4 et IPv6), **pas de port 22** |
| Volume EBS `/cache` | gp3 chiffré, **séparé du disque système**, monté par UUID, formaté seulement s'il est vierge |
| Bucket S3 | privé (accès public bloqué), chiffré, versionné, HTTPS obligatoire ; `cache/` (sauvegardes) et `deploy/` (paquets) |
| Dépôt ECR | privé, tags immuables, analyse des images, 10 images conservées |
| Rôle IAM | strict minimum, détaillé ci-dessous ; `bedrock:InvokeModel` limité aux ARN de `bedrock_model_arns` |

L'AMI est la dernière Amazon Linux 2023 au premier `apply`, puis figée
(`ignore_changes = [ami, user_data]`) : un `apply` futur ne remplace jamais l'instance. Pour la
fixer explicitement, recopiez `terraform output ami_id` dans `ami_id` de `terraform.tfvars`.

L'état Terraform est local (`terraform.tfstate`, ignoré par Git) et ne contient aucun secret :
les paramètres SSM sont créés hors Terraform. Pour le partager dans l'équipe, ajoutez un
backend S3 dans `versions.tf`.

Le premier démarrage (installation de Docker, du plugin Compose v5.6.0 dont l'empreinte
SHA-256 est vérifiée, montage du volume) prend 2 à 3 minutes.

## 2. Enregistrement DNS

Chez votre registraire, créez un enregistrement **A** : `bot.example.org` → `terraform output -raw public_ip`.
Vérifiez la propagation avant le premier déploiement, car Caddy demande le certificat
Let's Encrypt au démarrage :

```bash
dig +short bot.example.org     # doit afficher l'Elastic IP
```

## 3. Paramètres SSM

Toutes les valeurs vont sous le préfixe `/xamxam/`. Le nom du paramètre est le nom de la
variable d'environnement. Les secrets sont des **SecureString** ; ils sont saisis sans écho
avec `read -s` et transmis à la CLI par l'entrée standard : la valeur n'apparaît ni dans
l'historique du shell, ni dans la liste des processus.

```bash
REGION=eu-west-3

# Secrets (SecureString)
for name in WHATSAPP_TOKEN WHATSAPP_VERIFY_TOKEN WHATSAPP_APP_SECRET \
            KVICC_API_KEY LOG_HASH_KEY UNLIMITED_NUMBERS; do
  read -rsp "$name : " value; echo
  printf '%s' "$value" | aws ssm put-parameter --region "$REGION" \
      --name "/xamxam/$name" --type SecureString --value file:///dev/stdin --overwrite
done
unset value

# Configuration non secrète (String)
aws ssm put-parameter --region "$REGION" --type String --overwrite \
    --name /xamxam/LLM_PROVIDER --value bedrock
aws ssm put-parameter --region "$REGION" --type String --overwrite \
    --name /xamxam/BEDROCK_MODEL_ID --value "mistral.ministral-3-14b-instruct"
aws ssm put-parameter --region "$REGION" --type String --overwrite \
    --name /xamxam/BEDROCK_REGION --value "eu-west-1"
aws ssm put-parameter --region "$REGION" --type String --overwrite \
    --name /xamxam/WHATSAPP_PHONE_NUMBER_ID --value "<phone-number-id>"
aws ssm put-parameter --region "$REGION" --type String --overwrite \
    --name /xamxam/KVICC_TTS_URL --value "https://<hôte>/v1/audio/speech"
aws ssm put-parameter --region "$REGION" --type String --overwrite \
    --name /xamxam/KVICC_STT_URL --value "https://<hôte>/v1/audio/transcriptions"
```

Pour `LOG_HASH_KEY`, générez une valeur aléatoire (`openssl rand -hex 32`) et collez-la à
l'invite. Alternative sans terminal : console AWS → Systems Manager → Parameter Store →
« Créer un paramètre », type **SecureString**.

Au démarrage, `xamxam-secrets.service` lit ces paramètres et écrit un fichier par paramètre
dans `/run/xamxam` : un **tmpfs** (mémoire), appartenant à l'UID 10001 de l'utilisateur du
conteneur, en mode 400. Le conteneur le monte en lecture seule et `entrypoint.sh` exporte les
valeurs dans l'environnement du seul processus applicatif. Les secrets ne sont jamais écrits
sur disque et n'apparaissent pas dans `docker inspect`.

## 4. Premier déploiement

Attendez que l'instance soit enregistrée auprès de SSM (« Online »), puis lancez le
déploiement depuis la racine du dépôt, sur un commit propre :

```bash
aws ssm describe-instance-information --region eu-west-3 \
    --query 'InstanceInformationList[].[InstanceId,PingStatus]' --output text

deploy/aws/deploy.sh
```

`deploy.sh` :

1. construit l'image `linux/amd64`, taguée par le commit, et la pousse dans ECR ;
2. envoie dans le bucket le paquet de déploiement (Compose, Caddyfile, scripts, unités systemd) ;
3. lance sur l'instance, via SSM Run Command, `install.sh` qui installe les fichiers, active
   les services et le timer de sauvegarde, recharge les secrets, puis `docker compose pull`
   et `up` ; le déploiement échoue si le bot n'est pas en bonne santé (`/health`).

Les déploiements suivants se font de la même façon. Après la modification d'un paramètre SSM,
un nouveau `deploy.sh`, ou dans une session :
`sudo systemctl restart xamxam-secrets.service xamxam.service`.

## 5. Webhook chez Meta

Console Meta → votre application → **WhatsApp → Configuration → Webhook** :

1. URL de rappel : `https://bot.example.org/webhook` ;
2. Jeton de vérification : la valeur de `WHATSAPP_VERIFY_TOKEN` ;
3. Validez (Meta appelle `GET /webhook`), puis abonnez le champ **messages**.

## 6. Vérification

```bash
curl -s https://bot.example.org/health
# {"status":"ok","tts":"kvicc","bot_ready":true,"missing_variables":[]}
```

Envoyez ensuite une photo d'exercice au numéro WhatsApp : accusé de réception immédiat, puis
note vocale et réponse finale.

Journaux et état, dans une session Session Manager :

```bash
aws ssm start-session --region eu-west-3 --target "$(terraform -chdir=deploy/aws/terraform output -raw instance_id)"
sudo docker logs --tail 50 xamxam-bot-1        # une ligne « job {...} » par demande, sans contenu
sudo docker logs --tail 50 xamxam-caddy-1
systemctl status xamxam.service xamxam-secrets.service
systemctl list-timers xamxam-backup.timer
```

## Rôle IAM de l'instance

La politique gérée `AmazonSSMManagedInstanceCore` n'est **pas** utilisée : elle autorise
`ssm:GetParameter(s)` sur tous les paramètres du compte. Politique effective (`iam.tf`) :

| Bloc | Actions | Ressources |
| --- | --- | --- |
| Paramètres du projet | `ssm:GetParametersByPath`, `ssm:GetParameters`, `ssm:GetParameter` | `parameter/xamxam`, `parameter/xamxam/*` |
| Déchiffrement | `kms:Decrypt`, seulement si `kms:ViaService = ssm.eu-west-3.amazonaws.com` | clé gérée `aws/ssm` |
| Bucket de sauvegarde | `s3:ListBucket` ; `s3:GetObject`, `s3:PutObject` (pas de suppression) | ce bucket uniquement |
| Bedrock | `bedrock:InvokeModel` (utilisé par l'API Converse) | ARN listés dans `bedrock_model_arns` uniquement |
| Image | `ecr:GetAuthorizationToken` (`*`, imposé par AWS) ; `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchCheckLayerAvailability` | ce dépôt uniquement |
| Agent SSM | `ssm:UpdateInstanceInformation`, `ssmmessages:{Create,Open}{Control,Data}Channel`, `ec2messages:{Acknowledge,Delete,Fail}Message`, `ec2messages:GetEndpoint`, `ec2messages:GetMessages`, `ec2messages:SendReply` | `*` (imposé par AWS) |

Pas de `ssm:SendCommand`, pas de suppression S3, aucun accès aux autres paramètres ou buckets.

### Bedrock et accès du conteneur au rôle

Le bot tourne dans un conteneur : pour qu'il appelle Bedrock avec le rôle de l'instance, la
limite de sauts IMDSv2 vaut **2** (`imds_hop_limit`). Conséquence : le conteneur peut obtenir
les identifiants temporaires du rôle, donc toutes les permissions ci-dessus. Avec
`imds_hop_limit = 1`, le conteneur n'y a plus accès et Bedrock devient inutilisable : aucune
clé statique n'est prévue, par choix. IMDSv2 reste obligatoire dans les deux cas.

Région : aucun modèle open source de la liste blanche n'est proposé dans `eu-west-3` (Paris).
Utilisez par exemple `BEDROCK_REGION=eu-west-1` (Irlande) et l'ARN correspondant dans
`bedrock_model_arns` ; les photos et transcriptions sont alors traitées en Irlande (UE).

## Sauvegarde et restauration du cache

`xamxam-backup.timer` lance chaque jour vers 3 h (heure de l'instance, UTC) un
`aws s3 sync /cache → s3://<bucket>/cache/`. Rien n'est supprimé du bucket, et le
versionnage conserve les anciennes versions pendant 30 jours (`backup_retention_days`).

Sauvegarde immédiate : `sudo systemctl start xamxam-backup.service`.

**Restauration complète** (volume vide ou recréé), dans une session :

```bash
sudo /opt/xamxam/restore-cache.sh
```

Le script arrête le bot, copie le contenu du bucket dans `/cache`, rétablit le propriétaire
(UID 10001) puis redémarre le bot.

**Restaurer un fichier dans une version antérieure** (versionnage S3) :

```bash
aws s3api list-object-versions --bucket <bucket> --prefix cache/<chemin>
aws s3api get-object --bucket <bucket> --key cache/<chemin> --version-id <id> <fichier>
```

**Perte de l'instance** : le volume du cache est indépendant. Un `terraform apply` recrée
l'instance et réattache le volume existant sans le reformater ; relancez ensuite
`deploy/aws/deploy.sh`. **Perte du volume** : `terraform apply` en crée un vierge, puis
`restore-cache.sh` le remplit depuis S3.

## Coût mensuel estimé

Région eu-west-3 (Paris), à la demande, tarifs consultés en octobre 2026 :

| Poste | Calcul | Coût mensuel |
| --- | --- | --- |
| EC2 t3.small | 0,0236 $/h × 730 h | ≈ 17,20 $ |
| Disque système gp3 20 Go | 0,096 $/Go | ≈ 1,90 $ |
| Volume cache gp3 10 Go | 0,096 $/Go | ≈ 0,95 $ |
| Adresse IPv4 publique (Elastic IP) | 0,005 $/h × 730 h | ≈ 3,65 $ |
| S3 (sauvegardes < 1 Go, versions) | stockage et requêtes | < 0,10 $ |
| ECR (10 images, ≈ 4 Go) | 0,10 $/Go | ≈ 0,40 $ |
| SSM Parameter Store (paramètres standard) | gratuit | 0 $ |
| **Total** | | **≈ 24 $ par mois** |

Non inclus : Bedrock (facturé aux jetons, voir `python -m xamxam.eval llm`), l'API WhatsApp, et le trafic sortant au-delà de la franchise
mensuelle d'AWS. Les crédits CPU « standard » évitent toute facturation de dépassement ; une
instance réservée ou un Savings Plan d'un an réduit le poste EC2 d'environ un tiers.

## Test local de la pile

Sans compte AWS, avec Caddy en certificat interne (voir l'en-tête de
`deploy/aws/docker-compose.local.yml`). Les secrets factices doivent appartenir à
l'UID 10001, comme sur l'instance :

```bash
cd deploy/aws
docker run --rm -v "$PWD/.local:/l" alpine sh -c \
  'mkdir -p /l/secrets /l/cache && printf verif > /l/secrets/WHATSAPP_VERIFY_TOKEN &&
   chown -R 10001:10001 /l && chmod 500 /l/secrets && chmod 400 /l/secrets/*'
export XAMXAM_IMAGE=xamxam-bot:local XAMXAM_DOMAIN=localhost \
       XAMXAM_HTTP_PORT=8080 XAMXAM_HTTPS_PORT=8443 \
       XAMXAM_SECRETS_PATH="$PWD/.local/secrets" XAMXAM_CACHE_PATH="$PWD/.local/cache"
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --wait
curl -sk https://localhost:8443/health
curl -sk "https://localhost:8443/webhook?hub.mode=subscribe&hub.verify_token=verif&hub.challenge=42"
docker compose -f docker-compose.yml -f docker-compose.local.yml down
docker run --rm -v "$PWD:/d" alpine rm -rf /d/.local
```

## Suppression

`terraform destroy` supprime l'instance, l'Elastic IP **et le volume du cache**. Le bucket
de sauvegarde n'est pas supprimé tant qu'il contient des objets : videz-le d'abord si vous
voulez vraiment tout effacer. Les paramètres SSM se suppriment à part
(`aws ssm delete-parameters`).
