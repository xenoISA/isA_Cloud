# ============================================
# isA Cloud - Production State Backend
# ============================================

terraform {
  backend "s3" {
    bucket         = "isa-cloud-terraform-state-production"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "isa-cloud-terraform-locks"
    encrypt        = true
  }
}
