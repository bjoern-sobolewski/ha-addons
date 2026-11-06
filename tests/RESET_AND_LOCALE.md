# Shared quota reset and browser dates

CPAMC and Keeper use CLIProxyAPI for reset options, provider eligibility, redemption and account cooldown recovery. Upgrade both images together; Keeper does not fall back to spending through the generic API-call endpoint.

## Management API

Both endpoints require the existing management authentication and are private to the management listener:

- GET /v8/management/quota/reset-options?auth_index=... returns provider, Codex credits or Claude usage/status, selectedGrantId and organizationId.
- POST /v8/management/quota/reset accepts auth_index, provider (codex or claude), request_id (UUID), optional Codex credit_id, or Claude grant_id and organization_id.

The response contains code, optional windowsReset and recoveryFailed. Only confirmed reset/already_redeemed/already_used clears the account cooldown. A successful provider reset with failed cooldown recovery returns recoveryFailed; repeating its request returns the saved result.

OpenAI automatic selection omits credit_id. Explicit credit IDs are supported and validated. This preserves the provider default; it does not promise that OpenAI always consumes the earliest-expiring credit. Claude options are filtered by backend policy and selected using the provider next grant ID, with an ID-order fallback.

## Retry and persistence

Clients keep the exact request ID and choice for network errors or unknown results, including across a tab reload through sessionStorage. Changing that choice while the result is unresolved is rejected. A settled retry replays the stored result. Requests with a conflicting account/choice and concurrent requests for the same account are rejected.

The backend writes .quota-reset-journal.ledger under AuthDir before redemption. Keep this file with the persistent auth directory. Missing/unwritable storage or malformed journal data refuses redemption. No access tokens are stored in the journal. This is a single-process journal, not a distributed lock for multiple CPA replicas.

Unknown results may retry the same provider operation for ten minutes; after that, new operations remain blocked pending investigation. Do not delete the journal or change request IDs to bypass an ambiguous result: the provider may already have spent a credit. The journal retains up to 4,096 operations and refuses new ones at capacity. There is no automatic pruning or ambiguity-resolution UI.

## Date display

Both UIs obtain locale from navigator.languages and time zone from browser Intl defaults, independently of the application language. Displayed timestamps honor the browser hour cycle. Calendar-only aggregation keys retain their calendar identity and use browser date ordering; changing display preferences does not re-bucket stored daily statistics. Machine timestamps and API serialization remain unchanged. Raw log contents retain the provider text; parsed log timestamps use browser formatting.

## Verification

The Dockerfiles apply these patches after the other maintained patches and run frontend checks and the relevant Go suites. Backend reset tests use synthetic HTTP transports and cover automatic/explicit choice, eligibility, concurrent requests, replay after restart, uncertain results and storage failures. No real reset redemption is needed.

The isolated service suite can run with CPA_QUOTA_IMAGE=ha-cpa-shared-reset:local and KEEPER_QUOTA_IMAGE=ha-keeper-shared-reset:local using python tests/quota_flow.py (PyYAML and websockets required). See SSE.md for its setup and isolation guarantees.
