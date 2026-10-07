# Changelog

## 0.1.22

- Add weekly account reset history and API-equivalent delivered value to admin and read-only account details.
- Compare value per quota percentage point by model and outgoing Normal/Fast requested mode, with sample eligibility and coverage.
- Include permanently archived requests in quota history and index archive lookups; preserve unknown modes, incomplete pricing and unconfirmed resets.
- Retain detailed weekly charts for administrators; shorter windows are outside the new report.

## 0.1.21

- Count quota observation ages up every second on Auth Files using one shared local clock, preserving captured timestamps and API polling frequency.

## 0.1.20

- Show Fast requested from the captured outgoing tier, preserve raw response metadata in tooltips, and support outgoing-tier pricing across events, exports, archives, caches and overview totals. Historical rows remain uncaptured.

## 0.1.19

- Show a visible sparkline marker when a range contains only one observed bucket, including isolated known cache-rate points.
- Preserve actual samples and missing values without inventing historical chart data.

## 0.1.18

- Give Total Requests and Usage Limits equal widths, preventing the quota table from expanding its card.
- Preserve 234px top cards, compact quota rows, expanded sparkline and narrow-screen stacking across all reporting roles.

## 0.1.17

- Give each account's quota refresh button a translated, account-specific accessible label in all supported languages.

## 0.1.16

- Include the approved compact Overview layout and visible-tab automatic usage refresh control.
- Place a small refresh icon and age after remaining quota; retain keyboard-accessible provenance without a separate badge.
- Keep traffic quota polling alive after startup and cancel it cleanly on shutdown.
- Preserve API-provider cache reporting with account/type revalidation and separate OAuth history handling.
- Harden read-only session migration, report sanitization and CSV exports while preserving existing report filters and historical-key access.


## 0.1.15

- Align each quota window, remaining bar, percentage and info icon on one compact line, with a labeled Window header and a separate reset countdown.
- Include minutes in multi-day resets; show browser-local reset dates and live minutes/seconds since each window was last observed in its tooltip.

## 0.1.14

- Put Total Requests and a compact, scrollable Usage Limits table in the top row; show average RPM beside the request count and enlarge its graph.
- Show individual provider accounts, reported remaining quotas, reset countdowns and per-window freshness tooltips; omit reserve quota from Overview.
- Remove Daily Average and the separate RPM card; order the lower cards as TPM, Total Tokens, Cache Rate and Total Cost.
- Move Recent Activity below Usage Distribution in admin, individual-key and read-only overviews.

## 0.1.13

- Keep viewer assets rooted at the configured gateway prefix so reloading nested read-only pages loads the dashboard correctly.

## 0.1.12

- Add a Stay signed in checkbox to browser login forms: seven-day persistent cookies when checked, browser-session cookies otherwise.
- Keep reloads, multiple tabs and hidden tabs signed in without inactivity timers, heartbeat requests or tab coordination.

## 0.1.11

- Preserve read-only logins across restarts and updates until their original seven-day expiry.
- Revoke read-only sessions when the dashboard password changes or the role is disabled; retain logout and individual admin revocation.

## 0.1.10

- Synchronize client-key names from CPA across dashboards, sessions, exports and read-only reports.
- Retain revoked-key names and existing aliases when no shared name exists; archive conflicting aliases.
- Send administrative name edits from Keeper and Local Ranking to CPA; keep viewer access read-only.

## 0.1.9

- Automatically ingest account/window observations from CPA every five seconds, reusing the usage-header cache path.
- Poll cached quota every ten seconds in admin, individual-key and all-key read-only dashboards; pause hidden tabs and prevent overlap.
- Show capture source, timestamp, age and account label on hover/tap, with visible stale status.
- Preserve manual/scheduled fallback queries, independent window timestamps, read-only permissions and the API key selector.

## 0.1.8

- Add Request Events, Auth Files, AI Provider details and Local Ranking to the read-only dashboard.
- Reuse the existing request table and account drill-downs with credential edits, raw logs and administrative actions removed.
- Export sanitized request reporting as CSV or JSON with the selected time, key, model, account and result filters.
- Include historical and revoked keys in reporting filters without restoring authentication access.

## 0.1.6

- Add an API key dropdown to read-only Overview, Realtime and Analysis, defaulting to All API Keys.
- Apply the selected key to all usage reports while retaining shared provider quota and restricted access.

## 0.1.5

- Use the existing key dashboard layout for all-key read-only access: Overview, Realtime, Analysis and Provider quota.
- Include usage comparisons and analysis across client keys, OAuth accounts and API provider accounts, with generic labels.
- Retain server-enforced admin/write denial and individual key-viewer scope.

## 0.1.4

- Clarify that overview login requires the separate read-only password.

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
