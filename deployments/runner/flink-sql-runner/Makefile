# =============================================================================
# flink-sql-runner image — build / push / verify (xenoISA/isA_Cloud#255)
# =============================================================================
# Defaults target the GitHub Container Registry under the xenoISA org;
# override REGISTRY for customer Harbor mirrors.
#
# Examples:
#   make build
#   make push                                    # → ghcr.io/xenoisa/flink-sql-runner:<tag>
#   make push REGISTRY=harbor.customer.local/isa-platform
#   make verify                                  # confirms /opt/flink/usrlib/ has the runner jar
#   make checksums                               # emits sha256 lines for jars.txt (paste back manually)
# =============================================================================

# Image identity. Tag encodes the Flink + Operator + Iceberg versions so
# a `helm install` referencing this tag lines up with the chart matrix
# documented in the README.
IMAGE_NAME       ?= flink-sql-runner
IMAGE_TAG        ?= 1.20.0-runner-1.10.0-iceberg-1.7.2
REGISTRY         ?= ghcr.io/xenoisa
OPERATOR_VERSION ?= 1.10.0

IMAGE      := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
DOCKERFILE := Dockerfile
CONTEXT    := .

.PHONY: build push verify checksums clean help

help: ## Print this help (default).
	@awk 'BEGIN {FS = ":.*##"} /^[A-Za-z_-]+:.*##/ {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the image locally.
	docker build -f $(DOCKERFILE) \
	  --build-arg OPERATOR_VERSION=$(OPERATOR_VERSION) \
	  -t $(IMAGE) $(CONTEXT)

push: build ## Push the image to $(REGISTRY).
	docker push $(IMAGE)

verify: ## Spawn the image briefly and confirm the runner jar is present.
	docker run --rm --entrypoint /bin/sh $(IMAGE) -c \
	  'ls -la /opt/flink/usrlib/ && test -f /opt/flink/usrlib/flink-sql-runner.jar && echo OK'

# Regenerate sha256 checksums for every URL in jars.txt. Output is
# printed to stdout; review and paste back into jars.txt. (A future
# improvement is to let this command rewrite the file in place; for
# now we keep the human in the loop because the jars are signed by
# Apache release-management keys, and we want a manual sanity check
# before pinning.)
checksums: ## Compute sha256 for each jar URL and print jars.txt-formatted lines.
	@set -eu; \
	while IFS= read -r line || [ -n "$$line" ]; do \
	  case "$$line" in \
	    '#'*|'') continue ;; \
	  esac; \
	  url=$$(echo "$$line" | awk '{print $$1}'); \
	  jar=$$(basename "$$url"); \
	  echo "[checksums] $$jar" >&2; \
	  sha=$$(curl -fsSL "$$url" | sha256sum | awk '{print $$1}'); \
	  echo "$$url  $$sha"; \
	done < jars.txt

clean: ## Remove local image.
	docker rmi -f $(IMAGE) || true
