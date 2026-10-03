# CPA Usage Keeper setup

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

The overview shows aggregate requests, failures, tokens, estimated equivalent API cost, a request timeline, per-key usage and shared cached provider quota. Choose the last 24 hours, seven days or 30 days. Key labels are generated from Keeper's internal key IDs; historical deleted keys receive independent opaque labels. Actual keys, key fragments, aliases and provider credential identities are excluded. Costs are estimates, not additional subscription charges.

The read-only role has dedicated reporting endpoints and cannot access the admin APIs, even directly on the LAN. It cannot edit settings, credentials, key aliases, prices or sessions, reset statistics/quota, or trigger provider quota probes. Reports use the existing history and quota cache. Read-only sessions are revoked on every Keeper restart, including when you change or clear the password. Admin and client-key sessions retain their existing behavior. Admins can also revoke an individual read-only session in the LAN dashboard's session list.

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
