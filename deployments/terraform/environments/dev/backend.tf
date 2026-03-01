# ============================================
# isA Cloud - Dev State Backend
# ============================================

terraform {
  backend "s3" {
    bucket         = "isa-cloud-terraform-state-dev"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "isa-cloud-terraform-locks"
    encrypt        = true
  }
}
