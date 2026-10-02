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

Enable `viewer_dashboard_enabled` to start the restricted dashboard at container port **8082**, under `/keeper/`. Both options default to false. Leave the 8082 host mapping disabled when your tunnel can use add-on DNS directly. This listener only forwards client-token login/logout, session/version, viewer reads and frontend assets. Admin password login, admin APIs, and all other paths/methods return 404, even with an admin cookie. The full LAN dashboard continues to use its current root path.

For a locally managed Cloudflare tunnel, insert a path-specific ingress rule **before** the hostname's API rule:

```yaml
- hostname: your-api.example.com
  path: ^/keeper(/.*)?$
  service: http://YOUR_KEEPER_ADDON_DNS:8082
```

Keep the path prefix intact; the viewer listener handles it. Preserve `/v1` routing to the API gateway. Tunnel/add-on UIs must support path routing; a hostname-only additional-host entry cannot express this rule.

For the HA Cloudflared app's hostname-only **Additional Hosts**, instead enable `viewer_api_gateway_enabled` and point the API hostname's service to `http://YOUR_KEEPER_ADDON_DNS:8082`. This combined restricted listener serves `/keeper/` and forwards only `/v1/` to the companion CPA app's API-only port 8080 on the same host as `cpa_base_url`. It preserves WebSocket upgrades and unbuffered streaming, and blocks management paths. CPA does not need restarting. The three gateway/quota options are independent and default to false.

If an existing WAF rule requires a Bearer header for the entire API hostname, narrow that rule to API paths or exclude `/keeper` and `/keeper/…`; browsers log in with a POSTed key and then an HttpOnly session cookie. Keep API header protection in place and verify anonymous quota requests remain 401. Use HTTPS for remote access. Do not route the hostname directly to the full Keeper listener. Routing `/v1/` through Keeper makes that API hostname depend on Keeper being up; restoring its original CPA API gateway service bypasses this extra hop if Keeper is unavailable.

This HA build applies a reviewed local patch to upstream Keeper 1.15.9 at commit `3f1b29aa5b0b5284b75ec53573b5146cd50fea1b`, builds its embedded frontend and binary, and retains the upstream runtime and `/data` database layout.
