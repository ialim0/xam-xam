variable "region" {
  description = "Région AWS."
  type        = string
  default     = "eu-west-3"
}

variable "availability_zone" {
  description = "Zone de l'instance et du volume EBS du cache (ils doivent être dans la même)."
  type        = string
  default     = "eu-west-3a"
}

variable "project" {
  description = "Nom du projet : préfixe des ressources, du dépôt ECR et des paramètres SSM."
  type        = string
  default     = "xamxam"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.project))
    error_message = "Minuscules, chiffres et tirets uniquement (2 à 31 caractères)."
  }
}

variable "domain" {
  description = "Nom de domaine du webhook (enregistrement DNS A vers l'Elastic IP)."
  type        = string
}

variable "backup_bucket_name" {
  description = "Nom (unique au monde) du bucket S3 de sauvegarde du cache."
  type        = string
}

variable "instance_type" {
  description = "Type d'instance EC2."
  type        = string
  default     = "t3.small"
}

variable "ami_id" {
  description = <<-EOT
    AMI de l'instance. Laisser null pour prendre la dernière Amazon Linux 2023 au premier apply ;
    elle est ensuite figée (ignore_changes) : un apply futur ne remplace jamais l'instance.
  EOT
  type        = string
  default     = null
}

variable "root_volume_gb" {
  description = "Taille du disque système (Go)."
  type        = number
  default     = 20
}

variable "cache_volume_gb" {
  description = "Taille du volume EBS dédié au cache /cache (Go)."
  type        = number
  default     = 10
}

variable "container_uid" {
  description = "UID de l'utilisateur du conteneur du bot (Dockerfile) : propriétaire de /cache et des secrets."
  type        = number
  default     = 10001
}

variable "compose_version" {
  description = "Version du plugin Docker Compose installé sur l'instance."
  type        = string
  default     = "v5.6.0"
}

variable "compose_sha256" {
  description = "SHA-256 officiel de docker-compose-linux-x86_64 pour compose_version."
  type        = string
  default     = "40343e21ca777173e69cff5dbafeb37c6f81f3b0d57d9e597f036e95eb63e76a"

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.compose_sha256))
    error_message = "Empreinte SHA-256 hexadécimale attendue."
  }
}

variable "bedrock_model_arns" {
  description = <<-EOT
    ARN des modèles Bedrock que l'instance peut appeler (bedrock:InvokeModel, utilisé par
    l'API Converse). Exemple : arn:aws:bedrock:eu-west-1::foundation-model/mistral.ministral-3-14b-instruct.
    Pour un profil d'inférence inter-régions, ajouter l'ARN du profil ET ceux du modèle dans
    chaque région de destination. Liste vide : aucun accès à Bedrock.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for arn in var.bedrock_model_arns :
      can(regex("^arn:aws:bedrock:[a-z0-9-]+:(\\d{12})?:(foundation-model|inference-profile)/.+$", arn))
    ])
    error_message = "ARN Bedrock attendu (foundation-model ou inference-profile)."
  }
}

variable "imds_hop_limit" {
  description = <<-EOT
    Limite de sauts IMDSv2. 1 : les conteneurs n'accèdent pas aux identifiants du rôle de
    l'instance. 2 : nécessaire pour que le bot (dans Docker) appelle Bedrock avec ce rôle.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = contains([1, 2], var.imds_hop_limit)
    error_message = "1 ou 2."
  }
}

variable "backup_retention_days" {
  description = "Durée de conservation des anciennes versions des fichiers sauvegardés (jours)."
  type        = number
  default     = 30
}
