terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # État local par défaut (ignoré par Git). Pour un état partagé, voir docs/deploiement-aws.md.
}
