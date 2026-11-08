# CPA Usage Keeper setup

Administrators can inspect observed response stages, output activity and requested
tool names in **Live routing**, alongside the first observed and current user
prompt previews. Each text preview is limited to 240 characters. The start of an
older chat may not have been observed; tool-only continuations retain the last
user prompt. Generated answers, reasoning text and tool payloads are excluded.

In **Request Events**, expand the chevron beside a request to load its prompt
previews in a full-width detail row. Previews are captured for new requests and
remain only while the event is in hot storage. They are discarded on archival.
Both features require an administrator session. Read-only and API-key logins
cannot retrieve them, including by direct API calls; shared lists and CSV/JSON
exports omit prompt fields.

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

The read-only login opens the same dashboard layout as API Key view, with Overview, Realtime, Analysis, Request Events, Credentials, AI Provider, Local Ranking and Provider quota. Statistics cover all client keys, with key, OAuth account and API provider account breakdowns. The key dropdown includes current, revoked and historical keys; selecting a historical key does not restore its authentication access. Account/provider pages show usage, status, cached quota and request drill-downs. Account totals and provider quota are shared account information; the key dropdown filters request-based reporting. Client-key display names are included; actual keys, key fragments and provider credential identities are excluded. Costs are estimates, not additional subscription charges.

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

This HA build applies the reviewed `ha-v2.patch` to upstream Keeper main at commit `7b2b670f631335c0e2223af769c5abc04d731d8a` (including v2.0.3), builds its embedded frontend and binary, and uses the pinned v2.0.3 runtime. Persistent data stays under `/data`; the upgrade changes the database schema as described below.

## Automatic quota freshness

Supported Codex and Claude upstream quota headers, and Codex WebSocket quota
events, populate account-specific cached windows when present. Quota is optional;
missing observations do not erase existing windows. Late or equal observations
cannot replace newer windows. Manual and scheduled provider queries remain
available for idle accounts and providers without supported traffic metadata.

Quota views read backend caches every ten seconds, without provider queries.
Polling pauses while hidden, refreshes when visible, and does not overlap. Focus
or tap the remaining percentage to see the last update in seconds in a tooltip.
The percentage has no permanently visible refresh icon or age. Data is stale
after fifteen minutes or its reset time.
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

Open **Credentials → account → Weekly value** in the administrator or all-key
read-only dashboard. The report covers the last 90 days of recorded weekly
Codex windows. It shows the scheduled reset, when a later cycle was observed,
the last observed remaining percentage and its age, and recorded API-equivalent
value delivered during each cycle. A passed countdown alone does not confirm a
reset. Shorter windows and reserve pools are outside this report.

Model comparisons separate outgoing Normal (Auto/default) and Fast requested
modes. Canonical effective outgoing tiers take precedence when available, with the
maintained captured outgoing field as the historical fallback. Uncaptured
historical modes remain unknown. Estimates use only intervals
with one model/mode, complete pricing, no failed requests and at most one hour
between percentage changes. At least five percentage points, three intervals
and twenty requests are required. The report displays sample coverage and the
observed range; these eligibility floors do not establish statistical confidence.
Mixed intervals still contribute to delivered dollar totals.

API dollars per percentage point are total qualifying dollars divided by total
qualifying percentage points. Multiplying by 100 estimates a full allowance for
a similar workload. Context, caching, reasoning, changing quota rules and usage
outside the proxy can affect this estimate. API-equivalent values use each
request's stored Keeper cost, not a subscription invoice or confirmed billing
tier. Historical totals include permanently archived requests. Price edits apply
to new events; explicit v2 recalculation can update eligible recent hot events.
Unavailable historical data cannot be reconstructed.

This is shared account reporting across all client keys. The separate all-key
read-only login can view it without administrative controls; individual-key
sessions cannot access other users' usage. Report refresh reads the local
database and does not query or reset upstream quota. Administrators can expand
the existing detailed weekly observation charts beneath the summary.

The weekly cycle table leads with **API value / 1%**: total recorded API cost
inside observed quota-drop intervals divided by the percentage points consumed
in those same intervals. This is a blended observed average across models and
modes, including partial cycles; it does not use remaining quota to guess
unobserved consumption. The value column stacks this rate, total API value, and
the window's used percentage at its last observation (100 minus remaining).
Total value includes all recorded cycle requests, so it can exceed the
observed-drop numerator. **Observed quota used** separately shows the recorded
percentage drop, observed intervals and all cycle requests. Explanations and
pricing warnings appear in **Observation coverage**. Weekly dates and times,
including detailed observations and chart dates, follow browser locale
preferences independently of the dashboard language; chart days remain UTC.
No observed drop leaves the rate unavailable. When some usage cannot be priced,
the cycle table retains known dollars and the rate as a **≥ lower bound**, with
all observed percentage points still included in the denominator. Affected
models are listed; entirely unpriced values are unavailable, never zero. Missing
model prices or token details must be supplied for complete values. Full-allowance
estimates still require completely priced qualifying intervals.
Observation coverage retains last remaining quota, timestamps and partial coverage.

Consecutive reset-time updates while an unused weekly allowance stays at 100%
are combined in the weekly summary, including their recorded request counts
and API value. Five recent cycles are shown initially; Show older cycles expands
the remaining history. Detailed observation charts retain the original records.


The **Subscription value over time** chart appears before the cycle tables.
Its model dropdown supports multiple selections and starts with the two models
with the most recorded requests in this reporting period. Show all, Clear and
Top 2 controls are available inside the dropdown. Daily API value plots recorded
dollars in UTC calendar-day buckets; the current day is partial. The allowance
view uses qualifying quota samples from the trailing seven UTC days at each
date, with the same eligibility minimums as the table. Estimates never use future
samples and disappear when supporting samples age out. Incomplete daily pricing
appears as a gap. Current prices also apply to historical and archived requests.
Remaining quota has its own column before observed usage and API value.

Response timing is on the separate **Response speed** tab before Weekly value.
The previous combined weekly speed graph and separate Speed measurement selector
have been consolidated into this tab.

## Response speed

Open **Credentials → Codex account → Response speed** in the admin or all-key
read-only dashboard. Compare models and outgoing Normal/Fast requested mode
over 7, 14, 30 or 90 days; account request history is independent of quota windows.
The default is 7 days, total-time TPS and Normal + Fast modes. This is shared
account reporting across all client keys and includes archived requests. The
report reads local stored metadata only, without provider calls or prompts.

Use **Response speed over time** to choose total request time TPS, approximate
streaming phase TPS, recorded first-token time or completion time. The model
multi-select starts with the two most-used models across modes in this period;
other models remain selectable. Changing model selection recalculates workload
matching on the server. Clear shows no data instead of silently selecting all.
Workload filters and methodology are collapsed below the main controls/chart.

Time uses median and p90 (slow tail); speed uses median
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

### Text-to-image pricing

For GPT Image 2, choose **OpenAI text-to-image generation** in Model Pricing
Settings. Input is text tokens and output is image tokens. Configure rates from
the provider's Standard pricing table; no price is enabled automatically.
This style prices only `/v1/images/generations`, including CPA's recorded
`POST /v1/images/generations` format. Image edits, unknown endpoints
and unsupported cached-token usage stay unavailable because the retained token
counts do not distinguish text and image input. Reports preserve endpoint
groups, including archived weekly history, and retain known generation value
as a lower bound when other image usage cannot be priced.

Internal model labels without a verified API rate, such as `codex-auto-review`,
must remain unpriced unless an explicit valuation policy is configured. A free
subscription feature alone does not establish its API-equivalent token price.


### Upgrading to 0.2.0 (Keeper v2)

This wrapper builds the frozen upstream main commit
`7b2b670f631335c0e2223af769c5abc04d731d8a` (including v2.0.3)
on the upstream v2.0.3 runtime image. The runtime version identifies the
maintained build as `2.0.3-main.7b2b670-ha.1`.

Keep an HA backup including the add-on's data before upgrading. Keeper's staged
startup also makes and verifies its own pre-upgrade SQLite backup before legacy
conversion. Do not delete the backup directory or interrupt its storage access.
The startup status page remains available while schema migration, immutable
request-cost backfill and aggregate rebuild finish; reports open after those
stages complete. Failed initialization remains visible and can resume from
committed checkpoints. Allow adequate disk space for the database, backup and
SQLite temporary/WAL data.

Costs are now recorded when requests enter the database. Editing prices affects
new events. The v2 pricing editor provides explicit, bounded recalculation for
eligible recent hot events; older archived costs retain the migrated values.
Historical unpriced or unsupported image usage remains unavailable instead of
being assigned an invented value. Weekly values read these stored costs, and
captured outgoing request tiers remain distinct from effective/client/response
tiers.

Local key names, ranking profile overrides and period rows, read-only session
roles, and quota history remain in the same database. The upstream ranking
removal migration is deliberately retained as a non-destructive marker in this
maintained distribution. Public viewers continue to use their existing roles
and base path. Plugin-generated identities do not become client-key viewers.

For rollback, stop the add-on and restore the complete pre-upgrade database/data
backup together with the previous add-on image. Never run the previous v1 binary
against a v2-migrated database. Preserve the failed migrated database separately
for diagnosis when storage permits. No production migration is performed by the
repository tests or image build.

The previous 18 sequential local patches are consolidated in `patches/ha-v2.patch`.
Viewer scoping, names, sessions, quota freshness, outgoing tiers, weekly/daily
value, remaining history, navigation and performance reporting are carried
forward. Upstream v2 persisted costs and pricing controls replace the old
read-time pricing machinery and editor; frozen historical migrations remain
compatible with both stock upstream and this distribution's older databases.


## Combined provider statistics

In the LAN admin dashboard, select **Credentials → Provider stats**. Choose a
provider to combine recorded requests from all of its auth-file accounts,
including disabled and historical accounts. Account-list pagination, provider
filters and Enabled only do not limit this view. Select 7, 14, 30 or 90 days.

**Overview & API value** shows request counts, success/cache rates, tokens,
stored API-equivalent value, daily activity and model/mode totals. Missing
prices appear as lower bounds, or unavailable when every request is unpriced;
incomplete daily dollar values appear as chart gaps. Values are estimates, not
subscription charges. **Response speed** pools individual recorded requests
across accounts before calculating percentiles and workload comparisons.

Account quotas and resets stay separate because plans can have different
allowances. Retained archived requests are included. This admin-only view does
not change the restricted client-key or read-only reporting scope.

## Optional quota routing minimums

In the LAN Keeper administrator dashboard, open an account’s **Quota routing → Edit minimums**. Set an independent minimum remaining percentage for each observed Codex or Claude window. Blank turns that window off; zero stops at exhaustion. Settings apply to the whole account, including model-specific and reserve windows. Any configured window at or below its minimum excludes the account from new requests.

CPA saves settings in `/data/quota-policies.json`, independently of Keeper. Manual disable and priorities retain their existing meaning. Configured unknown windows, observations older than fifteen minutes, or passed resets exclude the account until a fresh observation arrives through existing traffic or scheduled/manual quota refresh. Restart retains settings but clears traffic observations, so configured accounts initially remain excluded. No new provider polling or probes are added.

The compact quota editor has independent **Rebalance session affinity** (default on) and **Reconnect WebSockets when safe** (default off) settings. CPA clears affinity across the affected scheduling pool after exclusion and after a higher-preference account recovers routing eligibility. Recovery uses actual model support, manual status, cooldown, weight and transport eligibility, requires 30 seconds of stable preference, and limits automatic reconnects to once per pool per two minutes. A quick recovery waits for that reconnect interval; repeated exclusions can still clear affinity immediately. Affinity clearing alone never closes a socket. With reconnect explicitly enabled, active responses, pending tool results and accepted steering finish on their existing account before the WebSocket closes with code 1012. Fresh requests enforce the minimum immediately; an explicitly draining pinned tool chain can finish on its existing account. The client must reconnect and resend full context before using another account. Clearing the minimums restores the original routing behavior. Keeper displays exclusion reasons and updates through its existing live event stream. Concurrent edits are rejected for review instead of silently overwriting another editor. These controls are administrator-only.


## Priority saves and session rebalancing

Keeper offers **Save priority**, which preserves existing sessions, and **Save & rebalance sessions**, which first persists priority in CPA and waits for its runtime view before rebalancing the account’s provider pool. Session affinity is cleared across that pool, including other accounts; generation checks prevent older selections or results from restoring stale bindings. The separate **Reconnect WebSockets when safe** checkbox is off initially. Affinity-only saves retain existing sockets and their pins. With that checkbox enabled, pins disappear when the safely drained connection retires. Other provider pools remain unaffected.

The administrator account pages show progress such as “Priority saved · codex · 5 sessions rebalanced · 2 waiting” through the existing live stream. Progress counts retired WebSocket sessions; clearing HTTP affinity takes effect on their next selection. Pending tools, queued requests, accepted steering and ambiguous protocol state can keep a session waiting until completion or client disconnect; CPA does not force a timeout that would interrupt them. A failed rebalance is reported separately from an already saved priority. Progress history is in memory and resets on server restart.

The installed Codex app-server was tested end to end with two synthetic accounts: a pending dynamic tool finished on its original account, the socket retired, and a subsequent turn replayed full conversation and tool context on the eligible account. Other clients must support reconnect/full-context recovery. This does not change the existing rule that a WebSocket-capable account can outrank a higher-priority HTTP-only account.

## Live routing

Open **Live routing** in the LAN administrator dashboard to see current HTTP requests, open WebSockets, queued/generating response work, pending tool outputs and safe drains together. Account distribution cards and pool/state/search filters help locate a connection. Select its session/request reference to inspect the observed routing reason, priority, candidate eligibility at selection and current work. Connection transport identifies the client-facing HTTP/WebSocket connection; it does not prove upstream transport.

The rebalance panel shows retired sessions and response/tool/protocol waits. Cached session affinity is listed separately because a binding can outlive its connection. Pause freezes the snapshot; Resume or Refresh reloads it. Errors retain the last successful snapshot and display a warning.

Activity is bounded in memory (4,096 connections, 200 recent events over ten minutes, up to 128 candidates and work items per connection) and resets on CPA restart. Tables show at most 200 matching rows; narrow the filters for larger sets. Session/client/request references use a runtime-specific keyed hash. Telemetry stores no prompts, request/response bodies, tool arguments/results, raw session IDs or client keys. Account labels and configured client aliases are administrator-only. This page and its API are unavailable to restricted viewers and the public API gateway. Opening it does not query providers or change routing rules.
