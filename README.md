# Home Assistant AI proxy apps

CLIProxyAPI and CPA Usage Keeper packaged for Home Assistant OS on Raspberry Pi 5 (64-bit) and amd64 machines. Images are built by GitHub Actions and published to GHCR. Upstream releases are pinned by version and image digest.

| App | Upstream | Purpose |
| --- | --- | --- |
| CLIProxyAPI | 8.0.10 | Model API, provider credentials, private management, API-only gateway |
| CPA Usage Keeper | 1.15.9 | Password-protected usage dashboard with persistent SQLite history |

These are experimental community wrappers, unaffiliated with the upstream projects. Container integration is tested; installation on a real Home Assistant OS device and actual provider OAuth/long Cloudflare streams still need deployment verification.

## Install

1. In Home Assistant, go to **Settings → Apps → Install app → ⋮ → Repositories** (older versions: Add-ons / Add-on Store).
2. Add `https://github.com/bjoern-sobolewski/ha-addons`.
3. Install **CLIProxyAPI** and **CPA Usage Keeper** after the [image build](https://github.com/bjoern-sobolewski/ha-addons/actions) succeeds. The GHCR packages must be public so Supervisor can pull them anonymously.
4. In CLIProxyAPI options, add one randomly generated `api_keys` entry per client and a separate `management_key`, each at least 24 characters. Start the app.
5. Find CLIProxyAPI's internal hostname from its app identifier: replace underscores with hyphens. For an identifier `abcdef12_cliproxyapi`, the hostname is `abcdef12-cliproxyapi`.
6. In Keeper options, set `cpa_base_url` to `http://abcdef12-cliproxyapi:8317`, use the same `management_key`, and set a separate `login_password` of at least 16 characters. Start Keeper and open `http://HOME_ASSISTANT_IP:8081`.
7. Add upstream credentials using the [CLIProxyAPI setup instructions](cliproxyapi/DOCS.md). Client API keys alone do not connect a model provider.

To manage client keys in the private management UI, set `api_key_source` to `management_ui` in HA options and restart. The app preserves saved client keys across restarts; HA keys only initialize a missing saved list. See [client key management and recovery](cliproxyapi/DOCS.md#client-api-key-management).

Generate secrets locally, for example `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Generate a different value for each credential. Store them in Home Assistant options and a password manager, never this repository.

## Cloudflare Tunnel

Point a dedicated hostname such as `codex.example.com` to **CLIProxyAPI port 8080**:

```yaml
# Existing locally managed Cloudflared app: merge into additional_hosts.
additional_hosts:
  - hostname: codex.example.com
    service: http://abcdef12-cliproxyapi:8080
```

For a remotely managed tunnel, add the equivalent published application route in the Cloudflare dashboard. Replace the illustrative hostname with your app's actual internal hostname. Follow the [Cloudflared app documentation](https://github.com/homeassistant-apps/app-cloudflared/blob/main/cloudflared/DOCS.md) for your tunnel mode.

Create an Access application for this hostname with a **Service Auth** policy accepting one service token per machine. Follow [Cloudflare's service-token instructions](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/). Each model request supplies:

```http
CF-Access-Client-Id: <machine's Access client ID>
CF-Access-Client-Secret: <machine's Access client secret>
Authorization: Bearer <machine's CPA client key>
```

Use `https://codex.example.com/v1` as the client API base URL. The gateway forwards `/v1/` requests with streaming buffering disabled, supports WebSocket upgrades, and returns 404 for other paths. Management (`/v0/management`, `/v8/management`) and `/management.html` are therefore unavailable through this route. Never point the public tunnel at port 8317 or Keeper's port.

Before connecting a real client, check that missing/incorrect Access credentials are rejected at Cloudflare, missing/incorrect CPA keys are rejected by CPA, a valid `/v1/models` request succeeds, and `/management.html` returns 404 even with valid credentials. Then test an actual long streaming request with your provider; the local gateway's one-hour read timeout does not override Cloudflare's limits.

## Storage and backups

CPA stores generated configuration and OAuth files under `/data`. Keeper stores its database, logs and rolling backups under `/data`. Home Assistant cold backups stop the apps while capturing their data. Treat backups as sensitive: they contain credentials and request metadata. Keeper's one-hour CPA queue retention helps short interruptions; it does not replace continuous collection or persist CPA's in-memory queue across CPA restarts.

## Development

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
docker build -t ha-cpa-test:local cliproxyapi
docker build -t ha-keeper-test:local cpa-usage-keeper
python tests/smoke.py
```

Smoke tests use random disposable credentials, a fake model provider, isolated Docker resources, and no paid model calls. They check API authentication, blocked management paths, a model response, SSE forwarding, Keeper authentication and usage ingestion, persistence across restarts, and graceful shutdown. Resources are removed when the test exits.

To update an upstream release, change its version and manifest digest in the Dockerfile, bump the app `version`, update the changelog, and push to `main`. Actions validates and tests amd64, then publishes both amd64 and arm64 under the app version tag. Home Assistant uses that exact version. Forks must update `repository.yaml` and the app image names/URLs to their own account.

## Internal documentation

Maintainer documentation is stored in a separate private repository, referenced
by the `.local-docs` submodule. It is optional for installation and development.
Automatic fetching is disabled so public checkouts do not require access.
Authorized maintainers can fetch the pinned documents from this project root:

```sh
git submodule update --init --checkout -- .local-docs
```

## Upstream and packaging references

- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) (MIT)
- [CPA Usage Keeper](https://github.com/Willxup/cpa-usage-keeper) (MIT)
- [Home Assistant app configuration](https://developers.home-assistant.io/docs/apps/configuration/)
- [Home Assistant internal networking](https://developers.home-assistant.io/docs/apps/communication/)

The wrapper code in this repository is MIT licensed. The upstream binaries retain their upstream licenses.
