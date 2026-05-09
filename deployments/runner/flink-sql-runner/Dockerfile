# =============================================================================
# flink-sql-runner image — Apache Flink 1.20 + connector + runner jars.
# Tracking issue: xenoISA/isA_Cloud#255.
#
# Two-stage build:
#   1. fetcher (alpine + curl): downloads jars per jars.txt and verifies
#      sha256 checksums when supplied (see jars.txt for the policy).
#   2. final (apache/flink:1.20): copies the verified jars into
#      /opt/flink/usrlib/ owned by `flink:flink`.
#
# The jars under /opt/flink/usrlib/ are auto-loaded by the Flink runtime,
# so FlinkSessionJob CRs from the flink-cdc-jobs chart (xenoISA/isA_Cloud#252)
# can reference `local:///opt/flink/usrlib/flink-sql-runner.jar` without
# extra mounts.
#
# Build:
#   make build
# Push (override REGISTRY for the customer's Harbor mirror):
#   make push REGISTRY=harbor.customer.local/isa-platform
# =============================================================================

# -------- Stage 1: fetch + verify jars --------
FROM alpine:3.19 AS fetcher

RUN apk add --no-cache curl coreutils

WORKDIR /jars
COPY jars.txt /jars.txt

# Download each jar and verify checksum (when supplied). Skips lines that
# start with `#` or are blank. A checksum of `-` skips verification for
# that single jar — useful for dev iteration but production builds
# should pin every checksum (regenerate via `make checksums`).
RUN set -eu; \
    while IFS= read -r line || [ -n "$line" ]; do \
      case "$line" in \
        '#'*|'') continue ;; \
      esac; \
      url=$(echo "$line" | awk '{print $1}'); \
      sha=$(echo "$line" | awk '{print $2}'); \
      jar=$(basename "$url"); \
      echo "[fetcher] downloading $jar"; \
      curl -fsSL --retry 3 --retry-delay 2 "$url" -o "/jars/$jar"; \
      if [ "$sha" != "-" ] && [ -n "$sha" ]; then \
        echo "[fetcher] verifying $jar"; \
        echo "$sha  /jars/$jar" | sha256sum -c -; \
      else \
        echo "[fetcher] WARNING: skipping checksum verification for $jar"; \
      fi; \
    done < /jars.txt

# -------- Stage 2: final image --------
FROM apache/flink:1.20.0-scala_2.12-java17

# The base image already runs as `flink` user (uid 9999) and has
# /opt/flink/usrlib/ as the standard auto-load directory.
COPY --from=fetcher --chown=flink:flink /jars/*.jar /opt/flink/usrlib/

# Sanity check — fail the build if the runner jar is missing.
RUN test -f /opt/flink/usrlib/flink-sql-runner.jar

USER flink
