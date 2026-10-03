# Changelog

## 0.1.3

- Add an optional separate read-only password for usage across all client keys and shared provider quota.
- Show aggregate totals, per-key usage, a timeline and 24-hour/seven-day/30-day reporting periods, without exposing keys or credential identities.
- Enforce a separate server role and restricted gateway routes; block admin APIs and writes even on the LAN.
- Revoke read-only sessions on restart and permit LAN administrators to revoke individual sessions.
- Keep overview access disabled until a distinct read-only password is configured.

## 0.1.2

- Add `viewer_base_path` for a custom public viewer URL prefix, retaining `/keeper` as the default.
- Apply the selected prefix to pages, assets, allowed APIs and session cookies; other prefixes remain closed.
- Reject invalid prefixes and the reserved `/v1` API path.

## 0.1.1

- Add an optional read-only provider quota tab to existing client-token sessions.
- Show separate account/window observations with remaining quota, reset and update times, and explicit stale/unavailable states.
- Add a disabled-by-default viewer-only `/keeper/` gateway on port 8082, with admin login and APIs blocked.
- Optionally forward `/v1/` on that gateway for tunnels with hostname-only routing, retaining WebSockets and SSE.
- Build pinned Keeper 1.15.9 source with a local patch; preserve the existing database and LAN dashboard.

## 0.1.0

- Package CPA Usage Keeper 1.15.9 for aarch64 and amd64.
- Configure authenticated access, persistent SQLite storage, and cold HA backups.
