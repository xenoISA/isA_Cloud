# ============================================
# Terraform Backend Configuration
# ============================================
# Stores Terraform state in S3 for team collaboration
# and state locking with DynamoDB

terraform {
  backend "s3" {
    # S3 bucket for state storage
    bucket = "isa-cloud-terraform-state-staging"
    key    = "staging/terraform.tfstate"
    region = "us-east-1"

    # DynamoDB table for state locking
    dynamodb_table = "isa-cloud-terraform-locks"

    # Enable encryption at rest
    encrypt = true

    # Optional: Use a specific profile
    # profile = "default"
  }
}

# Note: Before running terraform init, create these resources:
#
# 1. S3 Bucket:
#    aws s3 mb s3://isa-cloud-terraform-state-staging --region us-east-1
#    aws s3api put-bucket-versioning --bucket isa-cloud-terraform-state-staging --versioning-configuration Status=Enabled
#
# 2. DynamoDB Table:
#    aws dynamodb create-table \
#      --table-name isa-cloud-terraform-locks \
#      --attribute-definitions AttributeName=LockID,AttributeType=S \
#      --key-schema AttributeName=LockID,KeyType=HASH \
#      --billing-mode PAY_PER_REQUEST \
#      --region us-east-1
