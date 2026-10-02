# CLIProxyAPI setup

Set `api_keys` to a list of random client secrets and `management_key` to a different random secret (24+ characters each). Empty/default credentials deliberately prevent startup. Usage collection is enabled automatically for Keeper. The timezone defaults to Europe/Berlin.

## Client API key management

`api_key_source` defaults to `home_assistant`, which reapplies HA's `api_keys` on every startup. To manage client access in the private dashboard instead, select `management_ui` in HA options, save and restart the app. Existing client keys in `/data/config.yaml` are retained; HA's list is used only to initialize keys when the saved `access.api-keys` setting is absent.

In the dashboard's **Config Panel**, edit **API Keys** under **Basic Settings** and save. Add or remove client keys there; saved changes survive app restarts and updates. These are client access keys, separate from the keys on the upstream provider pages. Keep at least one client key of 24 or more characters, distinct from the management key. An empty or invalid saved list prevents startup and is never replaced with old HA keys.

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
