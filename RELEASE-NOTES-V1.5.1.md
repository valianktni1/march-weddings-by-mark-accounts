# Accounts v1.5.1 — HMRC sandbox workbench

Adds an optional HMRC test workspace while preserving manual PDF import,
independent Accounts numbering and the v1.5.0.4 address correction.

- Connect a generated HMRC test user using OAuth with PKCE.
- Encrypt connection tokens at rest; do not store HMRC login passwords.
- Show sandbox businesses, simulated obligations and security-header diagnostics.
- Prepare and explicitly approve a fictional cumulative sample update.
- Record accepted, rejected and unknown test outcomes, including HMRC correlation
  references; prevent automatic duplicate sends of the same review.
- Retrieve a test summary and distinguish canned responses from stateful tests.
- Separately preview the real accounting ledger cumulatively on the local server.
  Real accounting figures cannot be submitted through the test workspace.
- Default to disabled connection settings and a hardcoded sandbox-only transport.
  Live filing and annual tax returns are not implemented or enabled.

Setup: docs/HMRC-SANDBOX.md. Deployment: DEPLOY-V1.5.1-TRUENAS.txt.
Both backend and frontend need rebuilding. Existing live Compose secrets and
volumes must be preserved. The new environment entries are optional until
sandbox testing is configured.

No HMRC application credentials were supplied during implementation. Automated
API tests use mocked responses; actual OAuth and stateful sandbox testing remain
pending the developer-account setup. HMRC's production window restriction and
security-header requirements remain unresolved for live filing.

Validation: 82 backend tests passed; production frontend build succeeded.
Desktop and 390px mobile browser checks passed with mocked API responses:
confirmation gating, sample acceptance, local preview, no page errors or
horizontal document overflow. Backup/deployment blocks passed bash -n.
