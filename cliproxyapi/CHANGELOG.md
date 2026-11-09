# Changelog

## 0.1.27

- Identify whether reset failures originate in CPA or the upstream provider, with safe HTTP status and recovery guidance.
- Preserve uncertain reset results and the existing same-request retry journal without exposing raw provider errors.

## 0.1.26

- Count each WebSocket output event once at the downstream writer, preserving accurate activity counters through the shared HTTP execution path.

## 0.1.25

- Add bounded first/current user prompt previews and observed response stages, output activity and tool names to private live routing.
- Attach per-request previews to usage delivery, preserving user prompts through tool-only continuations without capturing generated answers or tool payloads.

## 0.1.24

- Remove the always-visible quota refresh icon and age. Show the last update in seconds only in a tooltip on the remaining percentage, with keyboard and touch access.

## 0.1.23

- Add a per-auth-file “Hide email in Keeper” switch to CPAMC. Persist the setting across refresh and re-login, publish a management-only privacy policy, and retain protection when credentials are deleted.

## 0.1.22

- Add private, bounded live routing telemetry for HTTP requests, WebSockets, queued responses, tool waits and safe session drains.
- Report observed account decisions, candidate eligibility and current session affinity without retaining request bodies, keys or raw session identifiers.
- Publish routing changes through the existing authenticated live stream; activity resets on restart.

## 0.1.21

- Add pool-scoped session rebalancing with safe response/tool/steering draining, affinity epochs and WebSocket reconnection.
- Separately persist affinity rebalancing (default on) and safe WebSocket reconnect (opt-in), with atomic edits and backward-compatible settings migration.
- Rebalance after quota exclusion and stable higher-preference eligibility recovery, with routing eligibility checks and reconnect throttling; use existing local observations without provider probes.
- Wait for saved priorities to reach runtime before explicit rebalancing; preserve the existing WebSocket-versus-priority routing rule.

## 0.1.20

- Persist optional per-account, per-observed-window quota minimums and enforce them across selection, retries, affinity and pinned WebSocket turns.
- Exclude configured unknown/stale/reset windows until fresh existing observations arrive; retain manual status and priorities.
- Add private policy management with atomic persistence and concurrent edit protection, without provider polling.

## 0.1.19

- Preserve object-shaped headers on credit-only quota observations for older cached management clients; explicitly cover null-header account rendering.
- Replace the default React Router crash screen with safe reload/dashboard recovery actions.

## 0.1.18

- Centralize Codex/Claude quota resets in the v8 Management API with provider eligibility checks, explicit grant/credit support, durable request replay protection and cooldown recovery. Keep automatic OpenAI credit selection as the default.
- Format CPAMC date/time displays using browser locale, hour cycle and time zone.

- Replace credential/provider health dots with taller green/red request-volume graphs that update in place.

- Add an authenticated private SSE stats stream. CPAMC refreshes cached quota, reset-credit counts, credential health and request/failure totals from backend notifications without extra provider queries.

## 0.1.17

- Integrate CLIProxyAPI 8.0.51 plus the frozen main fixes at `be2563ff74a40979a9aadc59d0b24cedc6ba2e81`; pin management UI 1.27.2 at `f154fa9380825c4fe94bc577a9abaa7e505f8875`. The backend includes unreleased post-8.0.51 changes.
- Include proactive Codex renewal, capacity-specific cooldowns, WebSocket continuity and early failover, protocol hardening, concurrent state protection, compression, transport isolation, translation and provider updates.
- Preserve account-bound Reconnect, settings and tracking identity, safe diagnostics, shared key names, native traffic quota age/provenance, outgoing-tier history and the 8 MiB upstream HTTP fallback. Serialize Reconnect saves with native renewal and keep browser recovery/name operations bound to their starting connection.
- Reconcile local patches with upstream v8 APIs, login storage and plan/reset controls; retain archived quota/reset guards and metadata validation fixes.

## 0.1.16

- Add Reconnect to existing Codex accounts in Auth Files so an expired or unusable refresh token can be replaced through a fresh sign-in without deleting the account.
- Verify the same account and retain its credential filename, usage tracking identity, settings, WebSocket preference and disabled state. Cancellation or a different account leaves the existing credential intact.

## 0.1.15

- Route self-contained Codex WebSocket requests of 8 MiB or larger over upstream HTTP before sending them, avoiding oversized-frame reconnect loops during compaction.
- Keep the client WebSocket open and retain HTTP conversation state for compaction, tool continuations and interruption. New connections with small requests still use upstream WebSockets.
- Preserve connection-local deltas on their existing upstream transport; never replay incomplete history over HTTP.

## 0.1.14

- Update CLIProxyAPI to 8.0.28 and the pinned management panel to 1.26.3.
- Include upstream WebSocket session/reload fixes, late interruption handling, transient HTTP/2 retry fixes, Codex SSE handling and configuration concurrency fixes.
- Preserve quota capture, shared key names, OAuth diagnostics, outgoing service-tier tracking and the API-only gateway.
- Update panel Axios to 1.20.0 with its security fixes; preserve retained Claude balances when newer traffic arrives during refresh.
- Retain the panel's new compact key layout, Claude balances and reset controls, plugin quotas and all six language catalogs.

## 0.1.13

- Update CLIProxyAPI from 8.0.10 to 8.0.22, including response.interrupt support, active upstream forwarding and HTTP cancellation.
- Reconcile local OAuth diagnostics and outgoing Fast-request tracking with upstream fixes; preserve quota capture, shared key names and the customized management panel.
- Keep the WebSocket open after an interrupted response so follow-up turns can continue.

## 0.1.12

- Merge newer request-derived quota into native account windows without losing plan, credits, renewal or reset controls.
- Show available quota with a refresh-account-data prompt when account details have not been loaded.
- Add a default-enabled Display options switch for the usage refresh icon and age.
- Read the management quota cache every ten seconds while visible without extra provider queries.

## 0.1.11

- Preserve primary token usage and cost for non-streaming Codex responses that include image-tool usage metadata.

## 0.1.10

- Capture the final outgoing Codex service tier after payload overrides for HTTP and WebSocket usage events; preserve client and response tier metadata.

## 0.1.9

- Add distinct Refresh account data and Refresh credentials actions; keep the original separate Reset quota confirmation and eligibility.
- Keep successful account data visible during refresh and preserve its observation time on failures.
- Add a tiny refresh icon and compact observation age beside native Auth Files quota percentages, preserving plan, renewal, credit balance and manual-reset controls.
- Show the actual provider observation timestamp and source on hover, focus or tap without triggering provider queries or resets.
- Use the viewer browserÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢s time zone and regional date/time preferences for observation details and Auth Files reset clocks.

## 0.1.8

- Restore the original Auth Files and Quota Management interface, including provider plan, credit balance, manual-reset expiry, native window labels and Reset quota controls.
- Keep traffic quota collection available to reporting without replacing management cards with cached traffic windows.
- Preserve shared client-key names and management session diagnostics.

## 0.1.7

- Keep quota observation details attached while keyboard focus scrolls a card into view, preserving Escape, blur and outside-click dismissal.
- Preserve native quota label typography regardless of stylesheet load order.

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
