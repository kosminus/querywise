# Optional bucket for exports / pg_dump backups. Private + encrypted + versioned.

resource "aws_s3_bucket" "data" {
  count  = var.create_s3_bucket ? 1 : 0
  bucket = local.bucket_name

  tags = { Name = local.bucket_name }
}

resource "aws_s3_bucket_public_access_block" "data" {
  count                   = var.create_s3_bucket ? 1 : 0
  bucket                  = aws_s3_bucket.data[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  count  = var.create_s3_bucket ? 1 : 0
  bucket = aws_s3_bucket.data[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "data" {
  count  = var.create_s3_bucket ? 1 : 0
  bucket = aws_s3_bucket.data[0].id

  versioning_configuration {
    status = "Enabled"
  }
}
