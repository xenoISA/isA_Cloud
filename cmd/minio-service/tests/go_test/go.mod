module github.com/isa-cloud/isa_cloud/cmd/minio-service/tests/go_test

go 1.25.0

require (
	github.com/isa-cloud/isa_cloud v0.0.0
	google.golang.org/grpc v1.76.0
	google.golang.org/protobuf v1.36.10
)

replace github.com/isa-cloud/isa_cloud => ../../../..
