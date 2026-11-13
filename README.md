# Home Assistant AI proxy apps

Community Home Assistant wrappers for [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
and [CPA Usage Keeper](https://github.com/Willxup/cpa-usage-keeper), supporting
amd64 and aarch64 systems. These wrappers are unaffiliated with the upstream projects.

## Installation

1. Add this repository in Home Assistant under **Settings → Apps → Install app → Repositories**
   (called **Add-ons** in older versions):
   `https://github.com/bjoern-sobolewski/ha-addons`.
2. Install the desired apps and follow their configuration guides:
   - [CLIProxyAPI](cliproxyapi/DOCS.md) — model API and provider management.
   - [CPA Usage Keeper](cpa-usage-keeper/DOCS.md) — usage reporting.

Keep administrative interfaces private and back up app data before upgrades.

## Development

Maintainer instructions and local tooling live in the private `.local-docs` submodule.
Source pins and patches are defined in the app Dockerfiles; builds and checks
are defined in [GitHub Actions](.github/workflows/build.yaml).

The wrapper code is MIT licensed. Upstream components retain their own licenses.
