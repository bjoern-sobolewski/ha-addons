# Changelog

## 0.1.1

- Add a client API key source option: Home Assistant or the management UI.
- Preserve management UI key additions and revocations across restarts, seeding from HA only when saved client keys are absent.
- Reject empty, malformed or insecure saved client key lists during startup rather than restoring revoked keys or disabling authentication.

## 0.1.0

- Package CLIProxyAPI 8.0.10 for aarch64 and amd64.
- Add an API-only streaming gateway and private management listener.
- Persist OAuth files and configuration and enable usage collection for Keeper.
