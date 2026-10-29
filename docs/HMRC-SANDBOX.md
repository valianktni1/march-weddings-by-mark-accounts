# HMRC MTD sandbox workbench — Accounts v1.5.1

This is a development workbench for one self-employed business using standard
6 April–5 April reporting. It is not HMRC-recognised filing software. It cannot
submit a real MTD update or an annual tax return. The API host is hardcoded to
HMRC's sandbox and production cannot be enabled through configuration.

## What is implemented

- Optional navigation entry **HMRC (test)**, available after Accounts sign-in.
- A read-only cumulative preview of the existing authoritative income, expense
  and mileage ledgers. Linked receipts remain excluded from duplicate totals.
- Separate, server-generated fictional sample figures: £1,000 turnover and £100
  expenses per elapsed sample quarter. Your actual accounts never enter the
  sandbox submission route, even if a client supplies alternative payload data.
- OAuth authorisation-code flow with PKCE and expiring, single-use state.
- Encrypted access/refresh tokens, server-side only; no HMRC password storage.
- Read sandbox businesses, simulated cumulative obligations, create/review/send
  a sample cumulative update, retrieve a sandbox summary and view sample history.
- Header diagnostics through HMRC's Test Fraud Prevention Headers API. A 200
  response with INVALID_HEADERS is shown as invalid, not as a successful check.
- Atomic review claiming prevents simultaneous duplicate submission of one
  review. A timeout or HTTP 5xx creates an unknown outcome, without blind retries.

DEFAULT scenarios simulate responses and do not prove data was stored. STATEFUL
scenarios require a matching test business and supported ITSA status. Neither
scenario fulfils any real-world tax obligation.

## Step 1: install without enabling the connection

Use DEPLOY-V1.5.1-TRUENAS.txt. The existing app continues to work without HMRC
credentials. The local cumulative preview does not need a connection.

The current single-Uvicorn-worker deployment is required. Do not add workers or
replicas without replacing the token-refresh lock with a distributed lock.

## Step 2: create developer credentials and a generated test taxpayer

1. Register/sign in to the [HMRC Developer Hub](https://developer.service.hmrc.gov.uk/).
2. Add a **sandbox application**, not a production application.
3. Subscribe to these sandbox APIs:
   - Business Details (MTD), version 2.0
   - Obligations (MTD), version 3.0
   - Self Employment Business (MTD), version 5.0
   - Test Fraud Prevention Headers, version 1.0
4. Register this redirect URI, matching APP_URL exactly:
   `https://accounts2026.weddingsbymark.uk/api/hmrc/callback`
5. Create an **individual** in HMRC's [test-user service](https://developer.service.hmrc.gov.uk/api-test-user), enrolled for MTD Income Tax. Use its generated National Insurance number, user ID and password. Do not use a real NINO or real Government Gateway credentials.
6. Retain the application's sandbox client ID and secret privately. These are
   unrelated to OpenAI API keys or a personal HMRC login.

## Step 3: configure the existing Dockge backend

Add the following environment entries to the **existing** backend service in
Dockge. Keep its existing database credentials, volumes, ports and settings.
Do not replace the live compose file with the example's placeholder passwords.

```yaml
HMRC_SANDBOX_ENABLED: "true"
HMRC_ENVIRONMENT: "sandbox"
HMRC_SANDBOX_CLIENT_ID: "YOUR_SANDBOX_CLIENT_ID"
HMRC_SANDBOX_CLIENT_SECRET: "YOUR_SANDBOX_CLIENT_SECRET"
HMRC_TOKEN_ENCRYPTION_KEY: "YOUR_GENERATED_FERNET_KEY"
HMRC_SANDBOX_NINO: "NINO_FROM_GENERATED_TEST_USER"
HMRC_SANDBOX_TEST_USER_CONFIRMED: "true"
HMRC_TRUST_EDGE_HEADERS: "false"
HMRC_VENDOR_PUBLIC_IP: ""
```

Generate a fresh encryption key on TrueNAS after installing the update:

```bash
docker exec accounts-2026-backend python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep the same key across restarts. Store a private copy outside the repository.
Changing it requires reconnecting. Do not send the key, client secret or test
user password in chat, commit them to GitHub or show them in screenshots.

Changing the configured client ID or test NINO invalidates the connection and
prepared sample reviews. Recreate the backend after saving settings in Dockge.

## Step 4: exercise the workflow

1. Open Accounts → HMRC (test).
2. Connect the generated test user using the HMRC sandbox sign-in page.
3. Load test businesses and select a self-employment test business ID.
4. Select the year/standard quarter and prepare a fictional sample review.
5. Read the sample totals; type `SEND SAMPLE TO SANDBOX` and send it.
6. Check history for accepted, rejected or unknown outcome and correlation ID.
7. Retrieve the test summary. For DEFAULT responses, the returned data is canned
   and may differ from the submitted sample. For persistence testing, create a
   test business with the Self Assessment Test Support API, configure a suitable
   test ITSA status, select STATEFUL and use that business ID.
8. Separately preview your own cumulative figures locally. They cannot be sent.

If a request times out, inspect history and retrieve the stateful test summary
before preparing another review. A record left at Sending after a restart is an
unresolved outcome, not proof of success. No automatic resubmission occurs.

## Security-header readiness

The browser supplies its persistent device UUID, user agent, screen/window size
and UTC offset. User identifiers and version metadata are included. Connection
details may be unavailable behind the current TrueNAS reverse proxies or over
LAN access. The app reports missing headers and does not invent values.

Only enable HMRC_TRUST_EDGE_HEADERS after checking the outermost proxy
**overwrites** x-hmrc-client-ip and x-hmrc-client-port with the actual public
client address and original TCP source port. Do not use the server's port 443 or
an internal proxy's port. Block direct backend access. Set HMRC_VENDOR_PUBLIC_IP
to the actual public ingress address, and review any extra public TLS hops.
This first implementation supports a simple single public ingress; multi-public-
proxy chains require further implementation and validation.

The current Accounts login has no MFA and this private app has no device licence
key. Gov-Client-Multi-Factor and Gov-Vendor-License-IDs are therefore unavailable.
Contact HMRC about unavailable header data as required by their specification;
a passing basic header test alone does not establish compliance or production
eligibility. Do not fill missing fields with placeholders.

OAuth callback access logging is disabled in the supplied Nginx config and
Uvicorn command. Also suppress callback query strings in the outer Nginx Proxy
Manager access logs; they contain a short-lived authorisation code and state.
Browser/device metadata is transmitted to HMRC only when running sandbox API
or header tests. Your bookkeeping preview stays on your own server.

## Storage and recovery

hmrc_connections and hmrc_oauth_states hold encrypted connection data and are
excluded from portable application backups. Keep the encryption key separately.
The sample audit collection hmrc_submissions is included in backups. It is
separate from invoices, bank transactions, tax-year close state and real filing
status. Connection changes are not a substitute for revoking authority in HMRC.
OAuth state is automatically expired by MongoDB; tokens can be removed with the
Disconnect button. Sample history currently retains the latest 50 records in
its UI; records are retained in the database for development evidence.

## What must happen before live filing can be considered

- Resolve the accounting/date/import/recovery issues identified in the review.
- Confirm the taxpayer's MTD status, business sources and reporting basis.
- Confirm production eligibility with HMRC. Their guidance currently says the
  window for new 2026/27 quarterly-update products has closed. No private-use
  exception or later-year approval has been obtained.
- Complete real sandbox integration testing, security-header review and HMRC's
  production-access process. No sandbox credentials were supplied during this
  implementation; automated tests use mocked HMRC responses.
- Implement the full required submission/retrieval, amendment and annual-return
  handoff workflow, durable production audit and reconciliation of unknown outcomes.
- Add proper category/tax treatment, refunds, accounting-method support and
  consolidated-expense eligibility checks. The sample payload's consolidated
  expenses are fictional; it is not a determination that a taxpayer qualifies.
- Review security, accessibility, privacy, operational support and API updates.

Production filing requires a separate implementation and explicit release;
changing an environment variable cannot enable it in this version.

## Official specifications reviewed 29 October 2026

- [MTD Income Tax service guide](https://developer.service.hmrc.gov.uk/guides/income-tax-mtd-end-to-end-service-guide/)
- [OAuth with PKCE](https://developer.service.hmrc.gov.uk/api-documentation/docs/authorisation/user-restricted-endpoints)
- [Self-employment v5 cumulative endpoint](https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/self-employment-business-api/5.0/oas/create_amend_cumulative_period_summary.yaml)
- [Cumulative request schema](https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/self-employment-business-api/5.0/oas/schemas/createAmendCumulativePeriodSummary/request.json)
- [Business Details v2](https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/business-details-api/2.0)
- [Obligations v3](https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/obligations-api/3.0)
- [Web app fraud-prevention headers](https://developer.service.hmrc.gov.uk/guides/fraud-prevention/connection-method/web-app-via-server/)
- [Unavailable header data](https://developer.service.hmrc.gov.uk/guides/fraud-prevention/getting-it-right/#missing-header-data)
- [Create Test User](https://developer.service.hmrc.gov.uk/api-documentation/docs/api/service/api-platform-test-user/1.0)
