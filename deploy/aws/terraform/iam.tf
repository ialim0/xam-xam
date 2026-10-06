# Rôle de l'instance, au strict nécessaire. Il ne contient PAS ssm:SendCommand : seul
# l'utilisateur qui déploie envoie des commandes. La politique gérée
# AmazonSSMManagedInstanceCore n'est pas utilisée car elle autorise ssm:GetParameter(s)
# sur tous les paramètres du compte.

locals {
  ssm_prefix    = "/${var.project}/"
  account_id    = data.aws_caller_identity.current.account_id
  partition     = data.aws_partition.current.partition
  parameter_arn = "arn:${local.partition}:ssm:${var.region}:${local.account_id}:parameter/${var.project}"
}

data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bot" {
  name               = "${var.project}-bot"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

resource "aws_iam_instance_profile" "bot" {
  name = "${var.project}-bot"
  role = aws_iam_role.bot.name
}

data "aws_iam_policy_document" "bot" {
  # 1. Lecture des paramètres SSM du projet uniquement (/xamxam/...).
  statement {
    sid       = "LireParametresDuProjet"
    actions   = ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"]
    resources = [local.parameter_arn, "${local.parameter_arn}/*"]
  }

  # 2. Déchiffrement des SecureString (clé gérée aws/ssm), seulement via SSM.
  statement {
    sid       = "DechiffrerParametres"
    actions   = ["kms:Decrypt"]
    resources = [data.aws_kms_alias.ssm.target_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.region}.amazonaws.com"]
    }
  }

  # 3. Bucket de sauvegarde uniquement : lister, lire (restauration, paquets de déploiement),
  #    écrire (sauvegarde). Pas de suppression.
  statement {
    sid       = "ListerBucketSauvegarde"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.backup.arn]
  }
  statement {
    sid       = "LireEcrireBucketSauvegarde"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.backup.arn}/*"]
  }

  # 4. Récupération de l'image depuis le dépôt ECR du projet. GetAuthorizationToken
  #    n'accepte pas de restriction par ressource.
  statement {
    sid       = "JetonECR"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "LireImageECR"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchCheckLayerAvailability",
    ]
    resources = [aws_ecr_repository.bot.arn]
  }

  # 5. Bedrock : uniquement les modèles listés dans var.bedrock_model_arns.
  dynamic "statement" {
    for_each = length(var.bedrock_model_arns) > 0 ? [1] : []
    content {
      sid       = "AppelerModelesBedrock"
      actions   = ["bedrock:InvokeModel"]
      resources = var.bedrock_model_arns
    }
  }

  # 6. Agent SSM : Session Manager et réception des commandes (Run Command).
  #    Ces actions n'acceptent pas de restriction par ressource.
  statement {
    sid = "AgentSSM"
    actions = [
      "ssm:UpdateInstanceInformation",
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
      "ec2messages:AcknowledgeMessage",
      "ec2messages:DeleteMessage",
      "ec2messages:FailMessage",
      "ec2messages:GetEndpoint",
      "ec2messages:GetMessages",
      "ec2messages:SendReply",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "bot" {
  name   = "${var.project}-bot"
  role   = aws_iam_role.bot.id
  policy = data.aws_iam_policy_document.bot.json
}
