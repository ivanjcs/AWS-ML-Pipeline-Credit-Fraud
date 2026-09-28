terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1" # Asegúrate de que coincida con la que pusiste en aws configure

  default_tags {
    tags = {
      Project     = "ChurnPrediction"
      Environment = "Dev"
      ManagedBy   = "Terraform"
    }
  }
}