# MinIO Service - Logic Contract

> Business Rules and Edge Cases for MinIO gRPC Service (Object Storage)

---

## Overview

This document defines the business rules for the MinIO gRPC service, covering bucket management, object operations, and presigned URLs.

---

## Business Rules

### BR-001: Multi-Tenant Bucket Isolation

**Description**: Buckets are isolated by organization through naming convention.

**Given**: A user creates/accesses a bucket
**When**: Bucket operation is performed
**Then**:
- Bucket name prefixed with `{org_id}-`
- Cannot access buckets from other organizations
- Audit log records all bucket operations

**Examples**:

| Input Bucket | Org ID | Actual Bucket |
|--------------|--------|---------------|
| `uploads` | `org-001` | `org-001-uploads` |
| `exports` | `org-002` | `org-002-exports` |

**Test Cases**:
- `TestCreateBucket_BR001_BucketPrefixedWithOrgId`
- `TestListBuckets_BR001_OnlyReturnsOrgBuckets`
- `TestGetObject_BR001_CannotAccessOtherOrgBuckets`

---

### BR-002: Object Key Namespacing

**Description**: Object keys are namespaced by user within organization bucket.

**Given**: A user uploads/retrieves an object
**When**: Object operation is performed
**Then**:
- Key optionally prefixed with `{user_id}/`
- Enables per-user folders within org bucket
- Full path: `{org_id}-{bucket}/{user_id}/{key}`

**Test Cases**:
- `TestPutObject_BR002_KeyNamespacedByUser`
- `TestGetObject_BR002_UserCanAccessOwnObjects`

---

### BR-003: Presigned URL Generation

**Description**: Temporary URLs allow direct client access without exposing credentials.

**Given**: A presigned URL is requested
**When**: GetPresignedURL is called
**Then**:
- URL valid for specified duration (default 15 minutes)
- URL contains signature for authentication
- Supports GET (download) and PUT (upload) methods
- URL expires after duration

**URL Types**:

| Method | Use Case | Default Expiry |
|--------|----------|----------------|
| GET | Download object | 15 minutes |
| PUT | Upload object | 15 minutes |

**Test Cases**:
- `TestPresignedURL_BR003_GeneratesValidGetURL`
- `TestPresignedURL_BR003_GeneratesValidPutURL`
- `TestPresignedURL_BR003_URLExpiresAfterDuration`

---

### BR-004: Object Metadata

**Description**: Objects can have custom metadata attached.

**Given**: A user uploads an object with metadata
**When**: PutObject is called
**Then**:
- Metadata stored with object
- Metadata returned on GetObject
- Content-Type auto-detected if not specified

**Reserved Metadata**:
- `Content-Type`: MIME type
- `Content-Length`: Size in bytes
- `Last-Modified`: Upload timestamp

**Test Cases**:
- `TestPutObject_BR004_MetadataStoredWithObject`
- `TestGetObject_BR004_MetadataReturned`
- `TestPutObject_BR004_ContentTypeAutoDetected`

---

### BR-005: Object Listing with Pagination

**Description**: List objects with prefix filtering and pagination.

**Given**: A bucket contains objects
**When**: ListObjects is called
**Then**:
- Objects filtered by prefix
- Results paginated (default 1000 per page)
- Continuation token for next page
- Delimiter support for folder-like navigation

**Test Cases**:
- `TestListObjects_BR005_FiltersByPrefix`
- `TestListObjects_BR005_PaginatesResults`
- `TestListObjects_BR005_SupportsDelimiter`

---

### BR-006: Object Versioning

**Description**: Object versions tracked when versioning enabled.

**Given**: Versioning is enabled on bucket
**When**: Object is updated
**Then**:
- New version created
- Previous versions accessible by version ID
- Delete creates delete marker (soft delete)

**Test Cases**:
- `TestPutObject_BR006_CreatesNewVersion`
- `TestGetObject_BR006_CanRetrieveByVersionId`
- `TestDeleteObject_BR006_CreatesSoftDeleteMarker`

---

### BR-007: Audit Logging

**Description**: All operations logged for audit trail.

**Given**: Any operation is performed
**When**: Operation completes
**Then**:
- Audit log sent to Loki
- Includes: timestamp, user_id, org_id, operation, bucket, key
- Does NOT include object content

**Test Cases**:
- `TestPutObject_BR007_AuditLogRecorded`
- `TestGetObject_BR007_AuditLogRecorded`

---

## Edge Cases

### EC-001: Invalid Bucket Name

**Given**: Bucket name contains invalid characters
**When**: CreateBucket is called
**Then**: Returns InvalidArgument error

**Invalid Names**:
- Less than 3 characters
- More than 63 characters
- Contains uppercase letters
- Contains special characters (except `-`)
- Starts/ends with hyphen

**Test Cases**:
- `TestCreateBucket_EC001_InvalidNameReturnsError`

---

### EC-002: Bucket Already Exists

**Given**: Bucket with same name exists
**When**: CreateBucket is called
**Then**: Returns AlreadyExists error

**Test Cases**:
- `TestCreateBucket_EC002_DuplicateReturnsAlreadyExists`

---

### EC-003: Bucket Not Empty

**Given**: Bucket contains objects
**When**: DeleteBucket is called
**Then**: Returns FailedPrecondition error

**Test Cases**:
- `TestDeleteBucket_EC003_NotEmptyReturnsError`

---

### EC-004: Object Not Found

**Given**: Object key does not exist
**When**: GetObject is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestGetObject_EC004_NonExistentReturnsNotFound`

---

### EC-005: Empty Object Key

**Given**: Empty string as object key
**When**: PutObject/GetObject is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestPutObject_EC005_EmptyKeyReturnsError`

---

### EC-006: Object Too Large

**Given**: Object exceeds max size (configurable, default 5GB)
**When**: PutObject is called via gRPC
**Then**: Returns InvalidArgument error (use presigned URL instead)

**Test Cases**:
- `TestPutObject_EC006_TooLargeReturnsError`

---

### EC-007: MinIO Unavailable

**Given**: MinIO server is down
**When**: Any operation is called
**Then**: Returns Unavailable error

**Test Cases**:
- `TestPutObject_EC007_MinioUnavailableReturnsError`

---

### EC-008: Presigned URL Expired

**Given**: Presigned URL has expired
**When**: Client uses URL
**Then**: MinIO returns 403 Forbidden (client-side)

**Test Cases**:
- `TestPresignedURL_EC008_ExpiredURLFails`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| MinIO Error | gRPC Code | Message |
|-------------|-----------|---------|
| BucketNotFound | `NotFound` | "bucket not found" |
| NoSuchKey | `NotFound` | "object not found" |
| BucketAlreadyOwnedByYou | `AlreadyExists` | "bucket already exists" |
| InvalidBucketName | `InvalidArgument` | "invalid bucket name" |
| BucketNotEmpty | `FailedPrecondition` | "bucket not empty" |
| AccessDenied | `PermissionDenied` | "access denied" |
| Connection error | `Unavailable` | "minio unavailable" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| CreateBucket | < 50ms | |
| ListBuckets | < 50ms | |
| PutObject (small) | < 100ms | < 1MB |
| PutObject (medium) | < 1s | 1MB - 100MB |
| GetObject (small) | < 50ms | < 1MB |
| ListObjects | < 100ms | Per page |
| GetPresignedURL | < 10ms | No I/O |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
