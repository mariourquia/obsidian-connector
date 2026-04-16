---
title: Wave 5 triage (Tasks 46-55)
status: verified
owner: mariourquia
last_reviewed: 2026-04-16
---

# Wave 5 triage

Wave 5 is the "permissions, team mode, marketplace, release readiness,
long-term positioning" band. Each task is classified below as
**ship-now** (scoped minimal, landable this release), **defer**
(requires team-mode substrate we explicitly do not have), or
**release-gate** (shipped as part of this release's polish).

## Classification

| # | Task | Status | Scope |
|---|------|--------|-------|
| 46 | Role and permission model foundations | defer | Single-user today. Role/permission gate needs multi-user tokens first. |
| 47 | Team mode configuration | defer | Same as 46. No team mode until there are multiple users to route between. |
| 48 | Connector / plugin marketplace polish | release-gate | Covered by v0.10.0 release notes + README refresh + marketplace.json version bump. |
| 49 | Template packs and opinionated starter kits | ship-now | Adopt the existing `templates/` directory as the canonical location; one new doc. |
| 50 | Better release and upgrade workflow | release-gate | v0.10.0 release notes follow RELEASE_TEMPLATE.md; upgrade path documented in CHANGELOG. |
| 51 | Team dashboards and manager-style views | defer | Requires team-mode data model (Task 47). |
| 52 | External integration extension points | defer | Needs a stable public API contract first; premature to lock. |
| 53 | Privacy, trust, and safety hardening pass | release-gate | Covered by explicit `PRIVACY.md` + `SECURITY.md` links in release notes; no new code. |
| 54 | Public / open-source readiness checklist | release-gate | Release notes include the "ready for others" checklist state. |
| 55 | Long-term roadmap packaging and strategic positioning | release-gate | One-paragraph roadmap note in release notes. |

## Why defer 46 / 47 / 51 / 52

The product spec explicitly lists "team collaboration workflows" and
"cloud-hosted multi-user architecture" as out-of-scope
(`PRODUCT_SPEC.md:62-63`). Any token-scoped permission model, team
configuration, or team dashboard presumes a multi-user primitive we
have not built and do not plan to build in this wave. Shipping
stubs now would lock a contract we cannot keep.

When those become real:

- Task 46 lands first: split the single Bearer token into per-user
  scoped tokens, carry `user_id` on every capture, adjust
  `device_sync_state` to key on `(user_id, device_id)` instead of
  `device_id` alone.
- Task 47 follows: a boot flag (`MODE=team`) that enables the new
  token surface and the manager view.
- Task 51 and 52 follow from there.

Task 37 (this release) intentionally stops at single-user
multi-device. It does not pretend to be the first step of team mode.

## Ship-now in this release

**Task 49 -- Template packs and opinionated starter kits:**

- Reaffirm `templates/` as the canonical location for Obsidian / Claude
  starter assets (daily-note scaffolds, exec-plan frontmatter, design-doc
  frontmatter).
- `docs/implementation/templates.md` already documents the layout;
  nothing new to write.
- `vault_presets.py` is the existing implementation of the 13 preset
  templates.

Marked ship-now because it is already done -- we are just making sure
the release notes mention it.

## Release-gate items

Tasks 48, 50, 53, 54, 55 are satisfied by the v0.10.0 release notes
rather than code changes. They gate the release, not a separate PR.
Contents:

- **48 (marketplace polish)**: `marketplace.json` version bump to 0.10.0
  with a refreshed description referencing Task 42 + Task 37 + Task 45.
- **50 (release / upgrade)**: release notes follow
  `.github/RELEASE_TEMPLATE.md`. Upgrade path in CHANGELOG.
- **53 (privacy / trust / safety)**: release notes link to `PRIVACY.md`,
  `SECURITY.md`, and `SBOM.md` as the trust surface for external users.
- **54 (open-source readiness)**: release notes include a `Ready for
  others?` checklist: LICENSE, CODE_OF_CONDUCT, CONTRIBUTING, issue
  templates, security policy, onboarding doc, first-run smoke path.
- **55 (long-term roadmap)**: one-paragraph roadmap note in release
  notes: what this release ships, what is next (multi-user), and what
  is explicitly out of scope (cloud-hosted SaaS).

## Out of scope for this release

- Any Task 46 / 47 / 51 / 52 code.
- A plugin marketplace submission workflow (still user-local via
  `pip install -e .` or the DMG).
- Cloud-hosted team mode.

## Follow-up thread

Track multi-user work in a single future exec-plan `wave-6-team-mode.md`
when there is a concrete user request for it. Until that signal arrives,
leaving these tasks unshipped is the correct posture. Shipping team-mode
primitives speculatively would lock choices the users have not yet made.
