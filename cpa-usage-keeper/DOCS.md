# CPA Usage Keeper setup

Request Events shows **Fast requested** when the captured outgoing Codex tier is
`priority` or `fast`. Its tooltip separates the client tier, upstream requested
tier, and raw upstream reported tier. Older events without outgoing capture show
the client value with `(client)`. Pricing rules can match `upstream_service_tier`
across events and reports. This records request intent, not a confirmed served
or billed tier.

Set `cpa_base_url` to the private **root** URL of the CLIProxyAPI app, e.g. `http://abcdef12-cliproxyapi:8317`. Do not add `/v1` and do not use the API-only gateway on port 8080. The actual hostname comes from your installed CPA app identifier with underscores replaced by hyphens.

Copy CPA's management secret into `management_key`. Set a separate `login_password` (16+ characters). Keeper always requires authentication. Start CPA first, then Keeper. Open the Keeper web UI on your trusted LAN at `http://HOME_ASSISTANT_IP:8081`. You can change or disable this host mapping in **Network** settings; ingress is not enabled in this release.

Keeper's SQLite database is `/data/app.db`; logs and automatic database backups also stay under `/data`. Daily backup and log retention defaults to seven days, adjustable in options. Home Assistant backups stop the app to capture a consistent database.

Keeper probes CPA's built-in Redis/RESP interface and falls back to the HTTP usage queue if that interface is unavailable. No separate Redis server is needed. Usage history starts with new requests after the apps are running; CPA's earlier in-memory usage is not guaranteed to be recoverable. Keep one Keeper collector per CPA to avoid competing consumers.

Keep the full dashboard on port 8080 (default LAN mapping 8081) on your trusted LAN/VPN. Authentication over the default LAN HTTP endpoint is unencrypted, so use a trusted network or HTTPS.

## Client-token quota view

Enable `viewer_quota_enabled` to add **Provider quota** to Keeper's existing API Key view. Users sign in with their active CPA client key; they do not need the Keeper admin password. Quota is shared across the configured accounts and all users, rather than being an individual client allowance. Accounts receive generic provider labels. Disabled/deleted accounts, account identities, credentials, upstream errors, raw responses, billing analytics and reset-credit controls are excluded.

The view reads Keeper's existing quota cache. It shows remaining amounts/percentages, reset times and the last observation. Observations older than 15 minutes or past their reset time are marked stale. Missing or unsupported provider observations are unavailable, never assumed to be zero. Configure Keeper's quota auto-refresh from the LAN admin dashboard if you want regularly refreshed observations. The viewer reload button does not make upstream provider calls.

## Optional public viewer path

Enable `viewer_dashboard_enabled` to start the restricted dashboard at container port **8082**, under `/keeper/`. Both options default to false. Leave the 8082 host mapping disabled when your tunnel can use add-on DNS directly. This listener only forwards client-token and read-only login/logout, session/version, dedicated viewer reads and frontend assets. Admin password login, admin APIs, and all other paths/methods return 404, even with an admin cookie. The full LAN dashboard continues to use its current root path.

## Read-only overview across client keys

Set `read_only_password` to a separate password of at least 16 characters to enable **Read-only overview** on the login page. It must differ from the Keeper admin password and CPA management secret. An empty value disables this access; it is empty by default. Share this password only with people authorized to see every client's usage. A CPA client key continues to grant only that key's usage view and the optional shared provider quota view.

The read-only login opens the same dashboard layout as API Key view, with Overview, Realtime, Analysis, Request Events, Auth Files, AI Provider, Local Ranking and Provider quota. Statistics cover all client keys, with key, OAuth account and API provider account breakdowns. The key dropdown includes current, revoked and historical keys; selecting a historical key does not restore its authentication access. Account/provider pages show usage, status, cached quota and request drill-downs. Account totals and provider quota are shared account information; the key dropdown filters request-based reporting. Client-key display names are included; actual keys, key fragments and provider credential identities are excluded. Costs are estimates, not additional subscription charges.

Request Events provides time, key, model, account and success/failure filters and CSV/JSON export of the same sanitized reporting data. Exports omit credential metadata, client addresses, request bodies, response bodies and raw logs. Local Ranking compares key usage without profile-editing or community participation controls. Language, theme, table column preferences and other display-only settings remain available.

The read-only role has dedicated reporting endpoints and cannot access the admin APIs, even directly on the LAN. It cannot edit settings, credentials, key aliases, prices or sessions, reset statistics/quota, or trigger provider quota probes. Shared names from CPA appear in dropdowns, charts, events, exports, sessions and Local Ranking. Missing shared metadata preserves existing Keeper aliases; explicit empty names clear them. Before synchronization replaces an alias, Keeper retains its first conflicting value in local `app_settings` under `api_key_names.previous_alias.<id>`. Revoked keys retain reporting names without regaining access. Unnamed read-only keys use generic labels. Admin edits in Keeper and Local Ranking write to CPA first and fail if CPA cannot save them. Allow a dashboard refresh after saving. Reports use the existing history and quota cache. Read-only sessions persist across Keeper restarts and updates until their original seven-day expiry; dashboard activity does not extend it. Changing or clearing the read-only password revokes existing read-only sessions. Admin and client-key sessions retain their existing behavior. Admins can also revoke an individual read-only session in the LAN dashboard's session list.

Browser login forms offer **Stay signed in**, unchecked by default. Checked uses a persistent seven-day cookie; unchecked uses a browser-session cookie without Expires or Max-Age. Reloads, multiple tabs and hidden tabs retain the login. Closing only Keeper tabs does not sign out, and browsers may restore session cookies when restoring a previous session. Both choices retain the server-side seven-day limit. No inactivity timer, heartbeat or tab coordination is added. Older API clients that omit `rememberMe` retain their existing persistent-cookie behavior.

For remote access, enable `viewer_dashboard_enabled` and use the same viewer prefix and HTTPS gateway described here. No additional hostname or WAF path exception is needed. Never publish the full admin listener. Leave the read-only password empty until you are ready to grant access; upgrading alone does not enable it.

Set `viewer_base_path` to choose another prefix, for example `/viewer-RANDOM_VALUE`. Use a single segment starting with a letter or digit and containing at most 64 letters, digits, hyphens or underscores, with no trailing slash. `/v1` is reserved. Generate a random value locally and save it in HA options rather than committing your deployed path to a public repository. The prefix is applied to pages, assets, allowed APIs and session cookies. Only the selected prefix is served; `/keeper/` returns 404 when another prefix is selected. Keep client-token authentication enabled regardless of the path's randomness.

For a locally managed Cloudflare tunnel, insert a path-specific ingress rule **before** the hostname's API rule:

```yaml
- hostname: your-api.example.com
  path: ^/keeper(/.*)?$
  service: http://YOUR_KEEPER_ADDON_DNS:8082
```

Keep the path prefix intact; the viewer listener handles it. Replace `/keeper` in the example with your `viewer_base_path` when customized. Preserve `/v1` routing to the API gateway. Tunnel/add-on UIs must support path routing; a hostname-only additional-host entry cannot express this rule.

For the HA Cloudflared app's hostname-only **Additional Hosts**, instead enable `viewer_api_gateway_enabled` and point the API hostname's service to `http://YOUR_KEEPER_ADDON_DNS:8082`. This combined restricted listener serves `/keeper/` and forwards only `/v1/` to the companion CPA app's API-only port 8080 on the same host as `cpa_base_url`. It preserves WebSocket upgrades and unbuffered streaming, and blocks management paths. CPA does not need restarting. The three gateway/quota options are independent and default to false.

If an existing WAF rule requires a Bearer header for the entire API hostname, narrow that rule to API paths or exclude the exact `viewer_base_path` and paths starting with `viewer_base_path + "/"`; browsers log in with a POSTed key and then an HttpOnly session cookie. Remove any exception for the old prefix when changing it. Keep API header protection in place and verify anonymous quota requests remain 401. Use HTTPS for remote access. Do not route the hostname directly to the full Keeper listener. Routing `/v1/` through Keeper makes that API hostname depend on Keeper being up; restoring its original CPA API gateway service bypasses this extra hop if Keeper is unavailable.

This HA build applies a reviewed local patch to upstream Keeper 1.15.9 at commit `3f1b29aa5b0b5284b75ec53573b5146cd50fea1b`, builds its embedded frontend and binary, and retains the upstream runtime and `/data` database layout.

## Automatic quota freshness

Supported Codex and Claude upstream quota headers, and Codex WebSocket quota
events, populate account-specific cached windows when present. Quota is optional;
missing observations do not erase existing windows. Late or equal observations
cannot replace newer windows. Manual and scheduled provider queries remain
available for idle accounts and providers without supported traffic metadata.

Quota views read backend caches every ten seconds, without provider queries.
Polling pauses while hidden, refreshes when visible, and does not overlap. Focus
or tap the quota detail control for the source, capture timestamp, relative age
and account label. Freshness controls follow the remaining amount instead of
occupying a separate badge column. Data is stale after fifteen minutes or its reset time.
Cache reads never update capture timestamps. Traffic caches are in memory and
can be unavailable after restart until traffic or a fallback query arrives.

Reporting never includes credentials. Administrative routes remain private;
individual-key reporting remains scoped and the all-key role remains read-only.

Overview places Total Requests and cached Usage Limits in equal-width cards,
stacking them on narrow screens. Its usage auto-refresh setting supports Off,
10, 30 or 60 seconds and runs only while the page is visible, without overlapping
usage refreshes or querying provider quota. Existing values and chart samples
remain visible during background refreshes. A range with one observed bucket
shows a point at its actual value; missing chart samples remain missing.

## Weekly quota value

Open **Auth Files → account → Weekly value** in the administrator or all-key
read-only dashboard. The report covers the last 90 days of recorded weekly
Codex windows. It shows the scheduled reset, when a later cycle was observed,
the last observed remaining percentage and its age, and recorded API-equivalent
value delivered during each cycle. A passed countdown alone does not confirm a
reset. Shorter windows and reserve pools are outside this report.

Model comparisons separate outgoing Normal (Auto/default) and Fast requested
modes. Uncaptured historical modes remain unknown. Estimates use only intervals
with one model/mode, complete pricing, no failed requests and at most one hour
between percentage changes. At least five percentage points, three intervals
and twenty requests are required. The report displays sample coverage and the
observed range; these eligibility floors do not establish statistical confidence.
Mixed intervals still contribute to delivered dollar totals.

API dollars per percentage point are total qualifying dollars divided by total
qualifying percentage points. Multiplying by 100 estimates a full allowance for
a similar workload. Context, caching, reasoning, changing quota rules and usage
outside the proxy can affect this estimate. Prices and pricing rules are the
current Keeper configuration, not a subscription invoice or confirmed billing
tier. Historical totals include permanently archived requests and are recalculated
if pricing changes; unavailable historical data cannot be reconstructed.

This is shared account reporting across all client keys. The separate all-key
read-only login can view it without administrative controls; individual-key
sessions cannot access other users' usage. Report refresh reads the local
database and does not query or reset upstream quota. Administrators can expand
the existing detailed weekly observation charts beneath the summary.

The weekly cycle table leads with **API value / 1%**: total recorded API cost
inside observed quota-drop intervals divided by the percentage points consumed
in those same intervals. This is a blended observed average across models and
modes, including partial cycles; it does not use remaining quota to guess
unobserved consumption. The separate **Total API value** column includes all
recorded cycle requests, so its value can exceed the observed-drop numerator.
No observed drop or incomplete interval pricing leaves the rate unavailable.
Observation coverage retains last remaining quota, timestamps and partial coverage.

Consecutive reset-time updates while an unused weekly allowance stays at 100%
are combined in the weekly summary, including their recorded request counts
and API value. Five recent cycles are shown initially; Show older cycles expands
the remaining history. Detailed observation charts retain the original records.


The **Value and speed over time** section offers shared model and mode filters.
Daily API value plots recorded dollars in UTC calendar-day buckets; the current
day is partial. The allowance view uses qualifying quota samples from the
trailing seven UTC days at each date, with the same eligibility minimums as the
table. Estimates never use future samples and disappear when supporting samples
age out. Incomplete daily pricing appears as a gap. Current configured prices
also apply to historical graph values, including archived requests.

Response speed is total output tokens divided by total end-to-end request time
for successful generation requests with positive output and valid durations,
matching Request Events. Waiting and reasoning time are included; this is not
streaming-only decode throughput. Time to first token is the mean of valid
captured timings. Each daily model/mode point requires at least three timing
samples; hover for sample counts. Missing timing remains unavailable. Historical
uncaptured modes stay separate. Solid lines indicate Normal, dashed lines Fast
requested, and dotted lines unknown modes. Graphs do not establish confirmed
provider execution tiers or change billing or pricing rules.


## Account performance

Open **Auth Files → Codex account → Performance** in the admin or all-key
read-only dashboard. Compare models and outgoing Normal/Fast requested mode
over 7, 30 or 90 days; account request history is independent of quota windows.
Existing Weekly value raw speed graphs remain available. Performance is shared
account reporting across all client keys and includes archived requests. The
report reads local stored metadata only, without provider calls or prompts.

Choose completion time, recorded first-token time, end-to-end output TPS or
approximate phase TPS. Time uses median and p90 (slow tail); speed uses median
and p10 (slow tail). Raw charts describe actual workload. The matched table
and optional matched chart use empirical weighted request distributions, not
an average of bucket/model percentiles. Failed requests remain counted and
are excluded from timings; non-generation events and invalid timings are excluded.

Matching uses common cells of input tokens (<8k, 8k–32k, 32k–128k, 128k+),
total output tokens (<256, 256–1,024, 1,024–4,096, 4,096+), cache-read share
(<50%, 50–90%, 90%+), exact recorded reasoning effort, streaming status and
executor/transport. Each eligible group contributes equally to a fixed reference
mix: average the groups' workload proportions after restricting to common cells.
Every group then receives those same cell weights. At least two captured-mode
groups, twenty timings per group and five per common cell are required. Unknown
modes and sparse groups retain raw results only. Coverage shows the actual
number/fraction of timings retained, and filters can narrow the compared models.
Missing recorded dimensions match only equally unknown values. Broad size
buckets cannot control all task differences, and sample floors are not confidence
guarantees or a comparison of answer quality.

Daily UTC points keep one fixed reference mix within the selected reporting
period. Raw daily points need three timings; matched
points need twenty overall and three in every reference cell. Missing evidence
is a gap rather than a changed mix or extrapolation. First/current days can be
partial. The reference mix describes the selected period, not a forecast.

Proxy timings exclude client network delays, external tool execution and entire
agent workflows. First token can be reasoning, tool arguments or a fallback
event; first visible text is not separately recorded. Output counts include
reasoning. End-to-end TPS includes all request time. Approximate phase TPS is
output / (request time − recorded first-token time), limited to streaming
requests with at least 32 output tokens and 250 ms after first token. It is
not measured visible-text decode throughput. Missing timings are not reconstructed.
