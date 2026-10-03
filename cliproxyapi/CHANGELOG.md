# Changelog

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
