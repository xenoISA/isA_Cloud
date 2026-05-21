# Self-Hosted GitHub Actions Runners (ARC) Runbook

> Sibling artifacts:
> [`deployments/kubernetes/local/arc/`](../../deployments/kubernetes/local/arc/) —
> controller + runner-scale-set values, namespaces, GitHub App Secret template,
> and the install script.
> Authorising issue: [xenoISA/isA_Cloud#288](https://github.com/xenoISA/isA_Cloud/issues/288)
> — Parent epic: [#284](https://github.com/xenoISA/isA_Cloud/issues/284).
> Design rationale: [`docs/adr/0004-arc-self-hosted-runners.md`](../adr/0004-arc-self-hosted-runners.md).

## What this covers

Self-hosted GitHub Actions runners on the local `isa-cloud-local` kind cluster,
deployed with **Actions Runner Controller (ARC)** using the modern
**scale-set** model (`gha-runner-scale-set-controller` +
`gha-runner-scale-set` Helm charts). Each queued CI job gets a fresh ephemeral
runner pod that is destroyed after the job — no state leaks between jobs, and
the scale set sits at zero pods when no CI is running.

This runbook covers:

1. Prerequisites (kind cluster + GitHub App).
2. GitHub App creation and installation on the `xenoISA` org.
3. Installing ARC (one command).
4. The `runs-on` label and how workflows target the runners.
5. Scaling.
6. Troubleshooting.
7. GitHub App private-key rotation.
8. Caveat — what ARC does NOT survive (account suspension).

## Scope of this artifact

The config in `deployments/kubernetes/local/arc/` is **deployable config
only**. The live deploy (creating the GitHub App, applying the Secret with a
real key, running the install script against the cluster) is performed by a
maintainer with `xenoISA` org-admin rights. Workflow migration to these
runners is a separate story ([#289](https://github.com/xenoISA/isA_Cloud/issues/289))
and is **not** done here.

## 1. Prerequisites

| Prerequisite | Who | Notes |
|--------------|-----|-------|
| Running kind cluster `isa-cloud-local` | developer | `.claude/skills/cluster_operations/scripts/setup-local.sh` |
| `kubectl`, `helm` (>= 3.8, OCI support) | developer | `brew install kubectl helm` |
| GitHub App registered + installed on `xenoISA` | **org admin** | See section 2 — one-time |
| GitHub App private-key `.pem` file | **org admin** | Downloaded once at App creation |

ARC needs the GitHub API reachable to receive jobs — it does not replace
GitHub, it replaces GitHub-*hosted* compute.

## 2. GitHub App setup (org-admin, one-time)

ARC authenticates as a **GitHub App** — not a PAT. A GitHub App has no monthly
token-rotation chore, scoped permissions, and a higher API rate limit.

### 2.1 Create the App

1. Go to **`xenoISA` org → Settings → Developer settings → GitHub Apps → New
   GitHub App**.
   Direct URL: `https://github.com/organizations/xenoISA/settings/apps/new`.
2. **GitHub App name**: `isa-arc-runners` (any unique name).
3. **Homepage URL**: the repo URL is fine, e.g.
   `https://github.com/xenoISA/isA_Cloud`.
4. **Webhook**: uncheck **Active** — ARC's scale-set model long-polls, it does
   not need an inbound webhook.
5. **Permissions** — set the minimum ARC needs:
   - **Repository permissions** → **Administration**: Read & write
     (required to register/remove repo runners).
   - **Repository permissions** → **Metadata**: Read-only (auto-selected).
   - **Organization permissions** → **Self-hosted runners**: Read & write
     (required for org-level runner scale sets).
   - **Organization permissions** → **Administration**: Read-only.
6. **Where can this GitHub App be installed?** → **Only on this account**.
7. Click **Create GitHub App**.

### 2.2 Capture the App ID and private key

1. On the App's settings page, note the numeric **App ID**.
2. Scroll to **Private keys → Generate a private key**. A `.pem` file
   downloads — **store it securely** (a password manager / secrets vault).
   This file is the only thing you cannot re-download; you can only generate a
   new one.

### 2.3 Install the App on the org

1. On the App's settings page → **Install App** → install on the **`xenoISA`**
   org.
2. Choose **All repositories**, or **Only select repositories** scoped to the
   isA repos. For the pilot ([#290](https://github.com/xenoISA/isA_Cloud/issues/290))
   start with `isA_Console`, `isA_MCP`, `isA_Vibe`.
3. After installing, the browser URL is
   `https://github.com/organizations/xenoISA/settings/installations/<INSTALLATION_ID>`.
   Note the numeric **installation ID**.

You now have the three values ARC needs: **App ID**, **installation ID**,
**private-key `.pem`**.

### 2.4 (Optional) Org runner group

To scope which repos may use the runners, create an org **runner group**
(`xenoISA` org → Settings → Actions → Runner groups) and restrict it to the
isA repos. The scale set joins the `Default` group unless `runnerGroup` is set
in `values/runner-scale-set.yaml`.

## 3. Install ARC (one command)

From the repo root, with the kind cluster running:

```bash
ISA_ARC_GITHUB_APP_ID=<APP_ID> \
ISA_ARC_GITHUB_APP_INSTALLATION_ID=<INSTALLATION_ID> \
ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH=~/secrets/isa-arc.private-key.pem \
  deployments/kubernetes/local/arc/scripts/install-arc.sh
```

The script is idempotent — re-running reconciles to the same state. It:

1. Verifies `kubectl` / `helm` / cluster reachability.
2. Applies the `arc-systems` and `arc-runners` namespaces.
3. Creates/refreshes the `arc-github-app` Secret from your key material.
4. `helm upgrade --install`s the controller into `arc-systems`.
5. `helm upgrade --install`s the runner scale set into `arc-runners`.

If you prefer to manage the Secret yourself, apply it from the template first
and run with `--skip-secret`:

```bash
cp deployments/kubernetes/local/arc/manifests/github-app-secret.template.yaml \
   deployments/kubernetes/local/arc/manifests/github-app-secret.local.yaml
# edit the .local.yaml with the real App ID / installation ID / .pem contents
kubectl apply -f deployments/kubernetes/local/arc/manifests/github-app-secret.local.yaml
deployments/kubernetes/local/arc/scripts/install-arc.sh --skip-secret
```

`*.local.yaml` is gitignored — never commit a filled-in copy.

### 3.1 Verify the install

```bash
kubectl -n arc-systems get pods                       # controller Running
kubectl -n arc-runners get pods                       # listener Running
kubectl -n arc-runners get autoscalingrunnerset       # scale set present
```

In GitHub, the runner scale set appears under
`https://github.com/organizations/xenoISA/settings/actions/runners` once the
listener has registered. With `minRunners: 0`, **no runner pods exist** until a
job is queued — that is expected.

## 4. The `runs-on` label

Workflows target a runner scale set by its **installation name** — the Helm
release name. This config installs the scale set with
`runnerScaleSetName: self-hosted`, so:

```yaml
jobs:
  build:
    runs-on: self-hosted
```

Four isA repos already use `runs-on: self-hosted` for their `deploy-kind`
jobs (`isA_Console` — `deploy-kind.yml` + `smoke.yml`, `isA_MCP`,
`isA_Vibe`). Keeping the scale-set name as `self-hosted` means those
workflows route to ARC **with zero workflow changes**.

Migrating the remaining `test` / `lint` / `docker` workflows to
`runs-on: self-hosted` is story
[#289](https://github.com/xenoISA/isA_Cloud/issues/289) — **do not change any
workflow as part of #288**.

## 5. Scaling

Scaling is set in `values/runner-scale-set.yaml`:

| Key | Default | Meaning |
|-----|---------|---------|
| `minRunners` | `0` | Idle pods. `0` = zero RAM burn when no CI runs. |
| `maxRunners` | `4` | Concurrency cap — protects the 3-node kind cluster. |

To change scaling, edit the values file and re-run the install script (or
`helm upgrade` the `isa-kind-runners` release directly). For the 19-repo
rollout ([#291](https://github.com/xenoISA/isA_Cloud/issues/291)), raise
`maxRunners` after confirming the kind nodes have headroom — each `dind`
runner pod requests 250m CPU / 512Mi and can burst to 2 CPU / 4Gi.

Per-runner resource envelopes live under `template.spec.containers[].resources`
in the same values file.

## 6. Troubleshooting

| Symptom | Check | Likely cause / fix |
|---------|-------|--------------------|
| Listener pod `CrashLoopBackOff` | `kubectl -n arc-runners logs -l app.kubernetes.io/component=runner-scale-set-listener` | Bad GitHub App credentials — verify App ID / installation ID / key in the `arc-github-app` Secret. |
| Scale set never appears in GitHub | listener logs | App not installed on the org, or missing **Self-hosted runners** org permission. |
| Jobs stuck `Queued`, no runner pod | `kubectl -n arc-runners get pods`; listener logs | Listener not connected, or `maxRunners` already saturated. |
| Runner pod `Pending` | `kubectl -n arc-runners describe pod <pod>` | kind node out of CPU/memory — lower `maxRunners` or per-runner requests. |
| `docker build` fails in a job | runner pod logs (`runner` + `dind` containers) | dind sidecar not ready — confirm `containerMode.type: dind` and that `arc-runners` is at PSA `privileged`. |
| `helm template` discovery error about `gha-rs-controller` | n/a | `controllerServiceAccount` must be set in `values/runner-scale-set.yaml` — it already is; do not remove it. |
| Controller not reconciling | `kubectl -n arc-systems logs deploy/arc-gha-rs-controller` | Controller `watchSingleNamespace` is `arc-runners`; the scale set must be installed there. |

Useful one-liners:

```bash
# Tail the controller
kubectl -n arc-systems logs -f deploy/arc-gha-rs-controller

# Tail the scale-set listener
kubectl -n arc-runners logs -f -l app.kubernetes.io/component=runner-scale-set-listener

# Watch ephemeral runner pods appear/disappear as jobs run
kubectl -n arc-runners get pods -w
```

## 7. GitHub App private-key rotation

The App's private key should be rotated periodically (and immediately if it
may have leaked). Rotation is zero-downtime — GitHub allows two active keys
during the overlap.

1. **`xenoISA` org → Settings → Developer settings → GitHub Apps →
   `isa-arc-runners` → Private keys → Generate a private key.** A new `.pem`
   downloads. Do **not** delete the old key yet.
2. Refresh the Kubernetes Secret with the new key — re-run the install script
   with the new `.pem` path (it rewrites the Secret in place):

   ```bash
   ISA_ARC_GITHUB_APP_ID=<APP_ID> \
   ISA_ARC_GITHUB_APP_INSTALLATION_ID=<INSTALLATION_ID> \
   ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH=~/secrets/isa-arc.NEW.private-key.pem \
     deployments/kubernetes/local/arc/scripts/install-arc.sh
   ```

   Or just the Secret, then restart the listener:

   ```bash
   kubectl create secret generic arc-github-app -n arc-runners \
     --from-literal=github_app_id=<APP_ID> \
     --from-literal=github_app_installation_id=<INSTALLATION_ID> \
     --from-file=github_app_private_key=~/secrets/isa-arc.NEW.private-key.pem \
     --dry-run=client -o yaml | kubectl apply -f -
   kubectl -n arc-runners rollout restart deployment \
     -l app.kubernetes.io/component=runner-scale-set-listener
   ```

3. Confirm the listener reconnects (section 3.1) and a test job runs.
4. **Only then**, delete the old key in the GitHub App settings.

The App ID and installation ID never change during key rotation.

## 8. Caveat — what ARC does NOT survive

ARC removes the dependency on GitHub-*hosted* compute (and its billing). It
does **not** make CI independent of GitHub itself: the scale-set listener
long-polls the GitHub Actions API for jobs. If GitHub-hosted billing escalates
from a spending block to a **full account suspension**, the Actions API stops
serving jobs and ARC has nothing to poll — runners go idle.

Surviving a full account suspension requires an independent CI path (repo
mirror + a non-GitHub CI engine). That is the explicit scope of story
[#293](https://github.com/xenoISA/isA_Cloud/issues/293) (repo-mirroring DR) —
it is **out of scope for #288**. #288 delivers the cost fix; #293 delivers the
availability fix.
