# =============================================================================
# flink-sql-runner image — Apache Flink 1.20 + connector + runner jars.
# Tracking issue: xenoISA/isA_Cloud#255.
#
# Three-stage build:
#   1. runner-build (maven:eclipse-temurin-17): clones the Apache Flink
#      Kubernetes Operator source at $OPERATOR_VERSION, compiles the
#      flink-sql-runner-example module, copies the resulting jar.
#      (Apache does NOT publish a pre-built flink-sql-runner.jar; we
#      build from source.)
#   2. fetcher (alpine + curl): downloads connector jars from Maven
#      Central per jars.txt, verifies sha256 when supplied (see
#      jars.txt for the policy).
#   3. final (apache/flink:1.20): copies the runner jar (from stage 1)
#      and connector jars (from stage 2) into /opt/flink/usrlib/ owned
#      by `flink:flink`.
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

# -------- Stage 1: build flink-sql-runner.jar from operator source --------
ARG OPERATOR_VERSION=1.10.0
FROM maven:3.9-eclipse-temurin-17 AS runner-build

ARG OPERATOR_VERSION
WORKDIR /build

# Download + extract the operator source tarball pinned by
# OPERATOR_VERSION. archive.apache.org is the canonical mirror; build
# overrides via --build-arg OPERATOR_VERSION=... when bumping.
ADD https://archive.apache.org/dist/flink/flink-kubernetes-operator-${OPERATOR_VERSION}/flink-kubernetes-operator-${OPERATOR_VERSION}-src.tgz /build/operator-src.tgz

RUN set -eu; \
    tar xzf /build/operator-src.tgz -C /build; \
    # The flink-sql-runner-example module lives under examples/ in the
    # operator source tree. Run Maven from the project root with `-pl`
    # + `-am` so the parent pom + any sibling deps build first.
    cd /build/flink-kubernetes-operator-${OPERATOR_VERSION}; \
    mvn -B -DskipTests \
      -pl examples/flink-sql-runner-example -am \
      package; \
    # The build output is examples/flink-sql-runner-example/target/.
    # Some Maven plugins also produce a `-shaded.jar` (fat jar with
    # deps) — prefer that when present, otherwise fall back to the
    # plain jar (excluding sources / javadoc / original).
    cd examples/flink-sql-runner-example/target; \
    JAR=$(ls flink-sql-runner-example-*-shaded.jar 2>/dev/null | head -n1); \
    if [ -z "${JAR}" ]; then \
      JAR=$(ls flink-sql-runner-example-*.jar 2>/dev/null | grep -vE "sources|javadoc|original" | head -n1); \
    fi; \
    test -n "${JAR}" || { echo "[runner-build] no flink-sql-runner-example-*.jar produced"; exit 1; }; \
    cp "${JAR}" /build/flink-sql-runner.jar; \
    test -f /build/flink-sql-runner.jar

# -------- Stage 2: fetch connector jars from Maven Central --------
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

# -------- Stage 3: final image --------
FROM apache/flink:1.20.0-scala_2.12-java17

# The base image already runs as `flink` user (uid 9999) and has
# /opt/flink/usrlib/ as the standard auto-load directory. Copy the
# runner jar (built in stage 1) and the connector jars (fetched in
# stage 2) into that directory.
COPY --from=runner-build --chown=flink:flink /build/flink-sql-runner.jar /opt/flink/usrlib/flink-sql-runner.jar
COPY --from=fetcher --chown=flink:flink /jars/*.jar /opt/flink/usrlib/

# Sanity check — fail the build if any required jar is missing.
RUN test -f /opt/flink/usrlib/flink-sql-runner.jar && \
    ls /opt/flink/usrlib/iceberg-flink-runtime-1.20-*.jar >/dev/null && \
    ls /opt/flink/usrlib/flink-sql-connector-kafka-*.jar >/dev/null && \
    ls /opt/flink/usrlib/flink-sql-avro-confluent-registry-*.jar >/dev/null

USER flink
