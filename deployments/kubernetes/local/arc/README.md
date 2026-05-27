# ARC — Self-Hosted GitHub Actions Runners (local / kind)

Deployable config for self-hosted GitHub Actions runners on the
`isa-cloud-local` kind cluster, using **Actions Runner Controller (ARC)** in
the modern scale-set model.

> Authorising issue: [xenoISA/isA_Cloud#288](https://github.com/xenoISA/isA_Cloud/issues/288)
> — Parent epic: [#284](https://github.com/xenoISA/isA_Cloud/issues/284).
> Full operational guide: [`docs/runbooks/arc-self-hosted-runners.md`](../../../../docs/runbooks/arc-self-hosted-runners.md).
> Design rationale: [`docs/adr/0004-arc-self-hosted-runners.md`](../../../../docs/adr/0004-arc-self-hosted-runners.md).

## Quick health check

```bash
deployments/kubernetes/local/arc/scripts/runner-status.sh
```

Read-only dashboard: cluster reachability → controller/listener health →
scale-set bounds and current scaling → runner pods → listener queue depth →
recent ephemeral runner assignments. Exits 0 healthy, 1 degraded (with
markers next to the broken component).

## Layout

```
arc/
├── values/
│   ├── controller.yaml          # gha-runner-scale-set-controller Helm values
│   └── runner-scale-set.yaml    # gha-runner-scale-set Helm values
├── manifests/
│   ├── namespaces.yaml          # arc-systems + arc-runners namespaces
│   └── github-app-secret.template.yaml   # GitHub App auth Secret — TEMPLATE ONLY
└── scripts/
    └── install-arc.sh           # one-command, idempotent installer
```

## Quick start

This is **config only**. The live deploy needs a GitHub App registered on the
`xenoISA` org, an org runner group named `isA CI`, and a running kind cluster
— see the runbook.

```bash
# from the repo root, kind cluster running:
ISA_ARC_GITHUB_APP_ID=<APP_ID> \
ISA_ARC_GITHUB_APP_INSTALLATION_ID=<INSTALLATION_ID> \
ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH=~/secrets/isa-arc.private-key.pem \
  deployments/kubernetes/local/arc/scripts/install-arc.sh
```

## `runs-on` label

The runner scale set name is `self-hosted`, so workflows target it with
`runs-on: self-hosted` — the label four isA repos already use for their
`deploy-kind` jobs. Access is restricted by the `isA CI` org runner group.
Workflow migration is story [#289](https://github.com/xenoISA/isA_Cloud/issues/289),
not done here.

## Security

`github-app-secret.template.yaml` is a **template** — placeholders only.
A filled-in copy must be named `*.local.yaml` (gitignored) and never committed.
The install script can create the Secret directly from the `.pem` file so no
key material is ever written to a repo file.
