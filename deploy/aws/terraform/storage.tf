# Bucket privé et chiffré : sauvegardes du cache (cache/) et paquets de déploiement (deploy/).
resource "aws_s3_bucket" "backup" {
  bucket = var.backup_bucket_name
  # Un bucket non vide n'est jamais supprimé par Terraform.
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket                  = aws_s3_bucket.backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backup" {
  bucket = aws_s3_bucket.backup.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versionnage : chaque sauvegarde garde l'historique, ce qui permet de revenir en arrière.
resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket     = aws_s3_bucket.backup.id
  depends_on = [aws_s3_bucket_versioning.backup]

  rule {
    id     = "anciennes-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.backup_retention_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "paquets-de-deploiement"
    status = "Enabled"
    filter {
      prefix = "deploy/"
    }
    expiration {
      days = 90
    }
  }
}

# HTTPS obligatoire pour tout accès au bucket.
data "aws_iam_policy_document" "backup_bucket" {
  statement {
    sid     = "RefuserSansTLS"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.backup.arn,
      "${aws_s3_bucket.backup.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "backup" {
  bucket     = aws_s3_bucket.backup.id
  policy     = data.aws_iam_policy_document.backup_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.backup]
}
