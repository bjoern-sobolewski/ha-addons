# CLIProxyAPI setup

Set `api_keys` to a list of random client secrets and `management_key` to a different random secret (24+ characters each). Empty/default credentials deliberately prevent startup. Usage collection is enabled automatically for Keeper. The timezone defaults to Europe/Berlin.

## Client API key management

Client-key names in **Access & Auth** are saved immediately on CPA and shared with Keeper. Existing names from the current browser are imported when this editor opens, only for keys without shared metadata. Server names and explicit cleared names take priority over old browser storage. Open the editor once in the browser that holds your old names to migrate them. Names are stored as SHA-256-keyed metadata in `/data/api-key-names.json`, separate from authentication and provider configuration. Revoking a key retains its name for historical reports; naming a key never grants access. Use names without credentials or secrets.

`api_key_source` defaults to `home_assistant`, which reapplies HA's `api_keys` on every startup. To manage client access in the private dashboard instead, select `management_ui` in HA options, save and restart the app. Existing client keys in `/data/config.yaml` are retained; HA's list is used only to initialize keys when the saved `access.api-keys` setting is absent.

In the dashboard's **Config Panel**, edit **Client API Keys (access.api-keys)** and save. Add or remove client keys there; saved changes survive app restarts and updates. These are client access keys, separate from the keys on the upstream provider pages. Keep at least one client key of 24 or more characters, distinct from the management key. An empty or invalid saved list prevents startup and is never replaced with old HA keys.

In `management_ui` mode, HA's `api_keys` list can be cleared after confirming that saved keys work. For recovery, select `home_assistant`, provide a valid client key list in HA and restart. This deliberately replaces the saved list, so remove revoked keys from HA before using recovery. The management key remains controlled by HA in both modes.

Port **8080** is the API-only gateway for your tunnel. Port **8317** is the complete CPA server, including management; Keeper connects to this port internally. Both host port mappings are disabled initially. Internal app communication continues to work without publishing host ports.

## Provider setup

For OAuth and dashboard setup, temporarily enable host port 8317 in the app's **Network** settings, restart, and open `http://HOME_ASSISTANT_IP:8317/management.html` from a trusted LAN. Use the management key to sign in, then configure providers or import their OAuth files. See [upstream documentation](https://github.com/router-for-me/CLIProxyAPI) for the individual providers' supported login/import flows. The dashboard is downloaded from the upstream management project on first access. Disable this host mapping after setup when LAN management is no longer needed. Keep it out of Cloudflare Tunnel and router forwarding rules.

Alternatively, place a private `providers.yaml` file in this app's `/addon_configs/<app-identifier>/` folder using a Home Assistant file editor or Samba. It is mounted at `/config/providers.yaml`. Use the current v8 provider layout, for example:

```yaml
api-keys:
  openai-compatibility:
    - name: my-provider
      base-url: https://my-provider.example/v1
      keys:
        - api-key: REPLACE_WITH_UPSTREAM_SECRET
      models:
        - name: upstream-model-id
          alias: my-model
```

Restart the app to read this file. Supported sections are `api-keys`, `oauth`, `routing`, `requests`, `client` and `multimedia`. A supplied section replaces the stored section of the same name; remove the file if you want future dashboard edits to that section to survive restarts. Wrapper-owned server, management, auth-directory, usage collection and streaming keepalive settings are reapplied from app options at startup. Client authentication follows `api_key_source`; other dashboard configuration is preserved in `/data/config.yaml`.

The upstream provider key is separate from both the CPA client API key and management key. OAuth files stay in `/data/auth` and are included in app backups. For multiple machines, assign distinct client keys; Keeper can then attribute usage by key.

## Troubleshooting

- Startup rejects options: supply sufficiently long secrets and keep management/client keys distinct.
- `/v1/models` is empty: configure an upstream provider and its supported models.
- Keeper has no data: verify the internal hostname and management key; send a new model request. Keeper automatically falls back to the HTTP usage queue on CPA v8.
- Connection refused from another app: use the app identifier with underscores replaced by hyphens and the appropriate internal port.
- API route returns 404 for management: expected on port 8080; use the private 8317 listener for management.

## Automatic quota freshness

Supported Codex and Claude upstream quota headers, and Codex WebSocket quota
events, populate account-specific cached windows when present. Quota is optional;
missing observations do not erase existing windows. Late or equal observations
cannot replace newer windows. Manual and scheduled provider queries remain
available for idle accounts and providers without supported traffic metadata.

Auth Files and Quota Management retain the original provider quota interface.
Provider queries supply plan, renewal, credit balance, manual-reset expiry and
native quota windows where supported; Reset quota retains the original
confirmation and eligibility checks. Traffic observations do not replace these
management cards or add primary/secondary cache rows. Shared client-key names
and management session diagnostics remain available.

Use Refresh account data inside the account panel to reload provider account
details. It is separate from Reset quota, which retains its confirmation and
credit checks. Refresh credentials in the card footer renews OAuth credentials;
it does not reload quota or mark account data as fresh. Failed account queries
keep the last successful snapshot and capture time visible with an error.

Auth Files adds a small refresh icon and compact age beside quota percentages.
Hover, focus or tap it for the provider observation timestamp and source.
The timestamp is captured when the quota response arrives; cache reads and
optional metadata enrichment do not refresh it. The indicator makes no provider
requests and does not reset quota. Dates use the viewer browser’s time zone and
regional formatting, including its 12/24-hour preference. Observations older
than fifteen minutes have a muted warning color.

Keeper reporting reads cached traffic observations without provider queries.
Traffic caches are in memory and can be unavailable after restart until traffic
or a fallback query arrives.

Reporting never includes credentials. Administrative routes remain private;
individual-key reporting remains scoped and the all-key role remains read-only.
