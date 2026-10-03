# Changelog

## 0.1.6

- Restore native quota typography, spacing and 6px green/amber/red meters.
- Show cached observation details through accessible quota window labels, without refresh badges or visible age text.
- Identify short, weekly and custom windows from duration metadata instead of primary/secondary order.
- Preserve sanitized invalid_grant classification and retry behavior.

## 0.1.5

- Replace corrupted quota text and separate freshness badges with a small inline refresh icon and age after the remaining amount.
- Validate quota numeric/time fields, bound cache eviction and shared name metadata, and reject observations from a previous provider.
- Preserve shared key names and management-only quota access.

- Show an OAuth Login action when Codex refresh tokens expire or are reused, including partial refresh-all failures.
- Avoid retrying terminal refresh-token failures and keep usable access tokens until their expiry.
- Record one safe warning per credential/failure condition and a recovery event without token bodies or account names.
- Ignore management 401s from an earlier CPAMC connection and record focused, credential-free diagnostics for current authentication failures.

## 0.1.4

- Place each client-key number beside its display name in Access & Authentication.

## 0.1.3

- Persist shared client-key names separately from authentication configuration.
- Import existing browser names in Access & Auth, preserving server names and cleared-name markers.
- Provide admin-only name reads/edits and hashed name metadata for Keeper synchronization.

## 0.1.2

- Capture supported HTTP quota headers and Codex WebSocket quota events in an account/window cache.
- Build a pinned CPAMC dashboard with ten-second cache polling and quota provenance, age and stale indicators.
- Keep management-only cache reporting and manual provider-query fallback.

## 0.1.1

- Add a client API key source option: Home Assistant or the management UI.
- Preserve management UI key additions and revocations across restarts, seeding from HA only when saved client keys are absent.
- Reject empty, malformed or insecure saved client key lists during startup rather than restoring revoked keys or disabling authentication.

## 0.1.0

- Package CLIProxyAPI 8.0.10 for aarch64 and amd64.
- Add an API-only streaming gateway and private management listener.
- Persist OAuth files and configuration and enable usage collection for Keeper.
