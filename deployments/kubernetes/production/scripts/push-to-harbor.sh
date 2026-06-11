#!/usr/bin/env bash
# Canonical push of a locally-built image into SN Harbor.
#
# WHY THIS EXISTS (the r17 saga):
#   Pushing to the `core.harbor.domain` HOSTNAME from outside the cluster hits
#   Harbor's redirect/proxy path, which 500s on the chunked blob upload
#   ("uploading layer chunked: 500 Internal Server Error" / "HTTP POST EOF").
#   This is NOT a network or auth problem and NOT fixed by retrying.
#   The fix (SN service-deployment-and-operations-playbook §3.1, Method A):
#   push to the Harbor LB **IP** directly with `skopeo --dest-tls-verify=false`.
#   No `docker login`, no daemon.json change, no Docker restart.
#
# USAGE:
#   ./push-to-harbor.sh core.harbor.domain/isa/isa-model:gpu-local-multimodal-20260611-r17
#   (arg = the image:tag exactly as tagged in the local docker daemon)
#
# CREDS (no secrets in the repo): tries, in order —
#   1) $HARBOR_USER / $HARBOR_PWD env (use these on a node / in CI)
#   2) the docker credential helper for $HARBOR_HOST (Docker Desktop keychain)
#
# On a cluster NODE (ssh root@10.60.64.11) Docker can also push directly once the
# CA is trusted (playbook §3.1 Method B); this script is for laptop/bootstrap use.
set -euo pipefail

HARBOR_IP="${HARBOR_IP:-10.60.65.10}"
HARBOR_HOST="${HARBOR_HOST:-core.harbor.domain}"

SRC="${1:-}"
if [[ -z "${SRC}" ]]; then
  echo "usage: $0 <image:tag-as-in-local-docker-daemon>" >&2
  echo "  e.g. $0 ${HARBOR_HOST}/isa/isa-model:<tag>" >&2
  exit 2
fi

# repo path after the registry host -> push to the IP under the same path
REPO_TAG="${SRC#*/}"                       # isa/isa-model:<tag>
DST="${HARBOR_IP}/${REPO_TAG}"

# --- resolve credentials ---
U="${HARBOR_USER:-}"
P="${HARBOR_PWD:-}"
if [[ -z "${U}" || -z "${P}" ]]; then
  cred_store="$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.docker/config.json"))).get("credsStore",""))' 2>/dev/null || true)"
  if [[ -n "${cred_store}" ]] && command -v "docker-credential-${cred_store}" >/dev/null 2>&1; then
    creds_json="$(echo "${HARBOR_HOST}" | "docker-credential-${cred_store}" get 2>/dev/null || true)"
    U="$(echo "${creds_json}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["Username"])' 2>/dev/null || true)"
    P="$(echo "${creds_json}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["Secret"])' 2>/dev/null || true)"
  fi
fi
if [[ -z "${U}" || -z "${P}" ]]; then
  echo "No Harbor creds. Set HARBOR_USER/HARBOR_PWD, or 'docker login ${HARBOR_HOST}' first." >&2
  exit 1
fi

echo "[push-to-harbor] ${SRC}"
echo "[push-to-harbor]   -> docker://${DST}  (Method A: IP + --dest-tls-verify=false, user=${U})"
exec skopeo copy --retry-times 5 --dest-tls-verify=false \
  --dest-creds "${U}:${P}" \
  "docker-daemon:${SRC}" "docker://${DST}"
