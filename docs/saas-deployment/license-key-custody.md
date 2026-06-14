# License Signing Key Custody (ADR 0008)

> Status: ready-for-design (2026-06-08). Companion to ADR 0008 (License &
> Entitlement Layer) and ADR 0007 (Artifact Delivery). Concerns the ed25519
> keypair used by `isa-license-sign` (`isa_common/license_sign.py`) and verified
> at runtime by `isa_common/license.py`.

## The keypair

A license is a `license.json` signed with an **ed25519 private key** and verified
locally — offline, no phone-home — against the matching **public key**
(`ISA_LICENSE_PUBKEY`). There is exactly one trust relationship:

| Half | Lives where | Consumed by | Sensitivity |
|---|---|---|---|
| **Private key** (`*.key`, PKCS8 PEM) | isA-side offline issuance only | `isa-license-sign sign` | Secret. Never ships, never enters a customer namespace. |
| **Public key** (`*.pub`, SubjectPublicKeyInfo PEM) | Baked into the image / mounted as ConfigMap | `isa_common.license` runtime verify | Non-secret. A leaked public key cannot forge a license. |

Generate with:

```bash
python -m isa_common.license_sign keygen --out-dir ./keys
#   keys/isa-license-ed25519.key  -> private, KEEP OFFLINE (written 0600)
#   keys/isa-license-ed25519.pub  -> public,  -> ISA_LICENSE_PUBKEY
```

## Private key — same custody as release signing (ADR 0007)

The private key is an **issuance secret**, not a deployment artifact. It stays
offline under the **same custody as release/artifact signing** (ADR 0007's
offline-bundle signing chain):

- Stored offline (HSM / hardware token / an offline secret store), **never** in a
  repo, container image, CI secret reachable from customer infra, or any
  customer-reachable surface. ADR 0008 §7 makes this a hard rule: the license is
  **never editable from isA_Admin** — authoring lives only in this offline tool.
- Used only on the issuance workstation when minting/renewing a `license.json`.
- The `keygen` subcommand writes the private key `0600`; keep it that way and back
  it up the way release-signing keys are backed up.

If the private key is ever lost, no new or renewed licenses can be issued until a
rotation (below). If it is ever **compromised**, rotate immediately — a holder can
forge entitlements for any image carrying the matching public key.

## Public key distribution — image bake / ConfigMap

The public key is the only half that travels with the deployment, exactly like
`ISA_EDITION` / `BRAND_*` (ADR 0008 §6). Two equivalent delivery paths:

- **Image bake** — embed `ed25519.pub` in the image and point
  `ISA_LICENSE_PUBKEY` at it. Strongest tamper-resistance (changing the trusted
  key requires a rebuild).
- **ConfigMap** (per ADR 0008 §6) — ship it as a non-secret ConfigMap and inject:

  ```yaml
  env:
    - name: ISA_LICENSE_PUBKEY
      valueFrom:
        configMapKeyRef: { name: isa-license-pubkey, key: ed25519.pub }
  ```

  The signed `license.json` itself rides the offline bundle (ADR 0007) and is
  mounted read-only at `ISA_LICENSE_FILE` (a ConfigMap — integrity comes from the
  signature, not from being a Secret).

`ISA_LICENSE_PUBKEY` may be passed either as the PEM text or, in deployment, via
the ConfigMap reference above; `isa_common.license` consumes the PEM directly.

## Rotation

Public-key rotation is a renewal-cadence chore, not a hot path:

1. `keygen` a new keypair offline.
2. Re-issue (re-sign) outstanding licenses with the **new private key**
   (`isa-license-sign sign` round-trip-verifies each before you ship it).
3. Distribute the **new public key**: swap the `isa-license-pubkey` ConfigMap (or
   rebuild the image) in each namespace and roll the pods.
4. Retire the old private key from active use once all live licenses are re-issued.

To rotate without a flag day, an image MAY carry multiple trusted public keys
(verify-any-of) during the overlap window; today `ISA_LICENSE_PUBKEY` holds a
single key, so plan rotation at the enterprise renewal boundary. Because verify is
fully offline, rotation never depends on the (flapping) customer VPN.

## Why this shape

- **Air-gapped-safe**: no activation server, no CRL, no egress — a leaked *public*
  key is harmless, and the private key never touches customer infra.
- **Tamper-evident config**: under the single-image-set profile model, the
  signature is the only thing distinguishing a licensed install from a copy
  (ADR 0008 Context). The round-trip self-check in `isa-license-sign` guarantees
  every emitted `license.json` actually verifies VALID before it leaves the
  issuance host.

## Status (2026-06-10)

- **Model A adopted** (one vendor-wide signing key — see
  [`licensing-model.md`](./licensing-model.md) §4).
- The vendor keypair has been generated (`isa-license-sign keygen`) and the
  **private key is in isA-side custody, outside any git repo and outside the SN
  cluster Vault**. It is the only secret in this system; renewal/re-issue requires it.
- First license issued: `license_id=sn-prod-2026` (SN, `on-prem-full`), round-trip
  VALID, ConfigMaps staged in `sn-cloud-production` (enforce not yet armed).
- This is currently laptop-side custody (a working stopgap). Promote to proper
  offline/HSM custody before issuing beyond SN, per the rotation guidance above.
