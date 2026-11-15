FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/CLIProxyAPI.git \
    && git fetch --depth 1 origin e96d4c4818851cf0e96d27b2bc8b67379e449d9e \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = e96d4c4818851cf0e96d27b2bc8b67379e449d9e
COPY patches/quota-traffic.patch /tmp/quota-traffic.patch
RUN git apply --check /tmp/quota-traffic.patch && git apply /tmp/quota-traffic.patch
COPY patches/key-names.patch /tmp/key-names.patch
RUN git apply --check /tmp/key-names.patch && git apply /tmp/key-names.patch
COPY patches/oauth-errors.patch /tmp/oauth-errors.patch
RUN git apply --check /tmp/oauth-errors.patch && git apply /tmp/oauth-errors.patch
COPY patches/release-review.patch /tmp/release-review.patch
RUN git apply --check /tmp/release-review.patch && git apply /tmp/release-review.patch
COPY patches/oauth-compatibility.patch /tmp/oauth-compatibility.patch
RUN git apply --check /tmp/oauth-compatibility.patch && git apply /tmp/oauth-compatibility.patch
COPY patches/session-cache-test.patch /tmp/session-cache-test.patch
RUN git apply --check /tmp/session-cache-test.patch && git apply /tmp/session-cache-test.patch
COPY patches/upstream-service-tier.patch /tmp/upstream-service-tier.patch
RUN git apply --check /tmp/upstream-service-tier.patch && git apply /tmp/upstream-service-tier.patch
COPY patches/upstream-compatibility.patch /tmp/upstream-compatibility.patch
RUN git apply --check /tmp/upstream-compatibility.patch && git apply /tmp/upstream-compatibility.patch
COPY patches/oversized-codex-http.patch /tmp/oversized-codex-http.patch
RUN git apply --check /tmp/oversized-codex-http.patch && git apply /tmp/oversized-codex-http.patch
COPY patches/codex-reconnect.patch /tmp/codex-reconnect.patch
RUN git apply --check /tmp/codex-reconnect.patch && git apply /tmp/codex-reconnect.patch
COPY patches/upstream-integration.patch /tmp/upstream-integration.patch
RUN git apply --check /tmp/upstream-integration.patch && git apply /tmp/upstream-integration.patch
COPY patches/live-stats.patch /tmp/live-stats.patch
RUN git apply --check /tmp/live-stats.patch && git apply /tmp/live-stats.patch
COPY patches/shared-quota-reset.patch /tmp/shared-quota-reset.patch
RUN git apply --check /tmp/shared-quota-reset.patch && git apply /tmp/shared-quota-reset.patch
COPY patches/quota-observation-compat.patch /tmp/quota-observation-compat.patch
RUN git apply --check /tmp/quota-observation-compat.patch && git apply /tmp/quota-observation-compat.patch
COPY patches/quota-policy.patch /tmp/quota-policy.patch
RUN git apply --check /tmp/quota-policy.patch && git apply /tmp/quota-policy.patch
COPY patches/session-rebalance.patch /tmp/session-rebalance.patch
RUN git apply --check /tmp/session-rebalance.patch && git apply /tmp/session-rebalance.patch
COPY patches/live-routing.patch /tmp/live-routing.patch
RUN git apply --check /tmp/live-routing.patch && git apply /tmp/live-routing.patch
COPY patches/keeper-email-privacy.patch /tmp/keeper-email-privacy.patch
RUN git apply --check /tmp/keeper-email-privacy.patch && git apply /tmp/keeper-email-privacy.patch
COPY patches/request-previews.patch /tmp/request-previews.patch
RUN git apply --check /tmp/request-previews.patch && git apply /tmp/request-previews.patch

COPY patches/account-errors-reset.patch /tmp/account-errors-reset.patch
RUN git apply --check /tmp/account-errors-reset.patch && git apply /tmp/account-errors-reset.patch

COPY patches/codex-voice.patch /tmp/codex-voice.patch
RUN git apply --check /tmp/codex-voice.patch && git apply /tmp/codex-voice.patch

COPY patches/codex-responses-controls.patch /tmp/codex-responses-controls.patch
RUN git apply --check /tmp/codex-responses-controls.patch && git apply /tmp/codex-responses-controls.patch

COPY patches/codex-terminal-receipts.patch /tmp/codex-terminal-receipts.patch
RUN git apply --check /tmp/codex-terminal-receipts.patch && git apply /tmp/codex-terminal-receipts.patch

COPY patches/codex-desktop-voice.patch /tmp/codex-desktop-voice.patch
RUN git apply --check /tmp/codex-desktop-voice.patch && git apply /tmp/codex-desktop-voice.patch

COPY patches/model-whitelist.patch /tmp/model-whitelist.patch
RUN git apply --check /tmp/model-whitelist.patch && git apply /tmp/model-whitelist.patch

COPY patches/cpa-upstream-compatibility.patch /tmp/cpa-upstream-compatibility.patch
RUN git apply --check /tmp/cpa-upstream-compatibility.patch && git apply /tmp/cpa-upstream-compatibility.patch

FROM golang:1.26-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY --from=source /src/go.mod /src/go.sum ./
RUN go mod download
COPY --from=source /src/ ./
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/client/codex/live ./internal/api/middleware ./internal/translator/codex/openai/responses
RUN --mount=type=cache,target=/root/.cache/go-build go vet ./internal/client/codex/live
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/config ./internal/kvstore ./internal/promptpreview ./internal/routinglive ./internal/sessionrebalance ./internal/live ./internal/quotatraffic ./internal/logging ./internal/refreshdiagnostic ./internal/auth/codex ./sdk/cliproxy/auth ./internal/runtime/executor/helps ./internal/api/handlers/management
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/redisqueue ./sdk/cliproxy/usage ./internal/runtime/executor -run "TestCodex|TestUsageQueue"
RUN --mount=type=cache,target=/root/.cache/go-build go test ./sdk/api/handlers/openai
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/api ./sdk/api/handlers -run 'TestManagementV8|TestRoutingActivity'
RUN --mount=type=cache,target=/root/.cache/go-build go test ./sdk/cliproxy -run TestAccountWhitelistModelRegistration
RUN --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=1 go build -buildvcs=false -ldflags="-s -w -X main.Version=8.0.72-ha.18" -o /out/CLIProxyAPI ./cmd/server
FROM alpine:3.20 AS panel-source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/Cli-Proxy-API-Management-Center.git \
    && git fetch --depth 1 origin 3d893ec88938c3ceef200a15be6af8cf972564b3 \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 3d893ec88938c3ceef200a15be6af8cf972564b3
COPY patches/cpamc-ha-integration.patch /tmp/cpamc-ha-integration.patch
RUN git apply --check /tmp/cpamc-ha-integration.patch && git apply /tmp/cpamc-ha-integration.patch
COPY patches/cpamc-live-stats.patch /tmp/cpamc-live-stats.patch
RUN git apply --check /tmp/cpamc-live-stats.patch && git apply /tmp/cpamc-live-stats.patch
COPY patches/cpamc-browser-locale-shared-reset.patch /tmp/cpamc-browser-locale-shared-reset.patch
RUN git apply --check /tmp/cpamc-browser-locale-shared-reset.patch && git apply /tmp/cpamc-browser-locale-shared-reset.patch
COPY patches/cpamc-route-recovery.patch /tmp/cpamc-route-recovery.patch
RUN git apply --check /tmp/cpamc-route-recovery.patch && git apply /tmp/cpamc-route-recovery.patch
COPY patches/cpamc-keeper-email-privacy.patch /tmp/cpamc-keeper-email-privacy.patch
RUN git apply --check /tmp/cpamc-keeper-email-privacy.patch && git apply /tmp/cpamc-keeper-email-privacy.patch
COPY patches/cpamc-quota-tooltip.patch /tmp/cpamc-quota-tooltip.patch
RUN git apply --check /tmp/cpamc-quota-tooltip.patch && git apply /tmp/cpamc-quota-tooltip.patch
COPY patches/cpamc-model-whitelist.patch /tmp/cpamc-model-whitelist.patch
RUN git apply --check /tmp/cpamc-model-whitelist.patch && git apply /tmp/cpamc-model-whitelist.patch
COPY patches/cpamc-upstream-compatibility.patch /tmp/cpamc-upstream-compatibility.patch
RUN git apply --check /tmp/cpamc-upstream-compatibility.patch && git apply /tmp/cpamc-upstream-compatibility.patch
FROM node:24-alpine AS panel-builder
WORKDIR /src
COPY --from=panel-source /src/package.json /src/bun.lock ./
RUN npx --yes --package=bun@1.4.3 bun install --frozen-lockfile
COPY --from=panel-source /src/ ./
RUN npx --yes --package=bun@1.4.3 bun run verify
FROM eceasy/cli-proxy-api:v8.0.72@sha256:7cac48fd7f3ac0b7b6b73508d92179e29454087d9af81eb9a5c9fb50cdd87bc8
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-yaml nginx-light ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /out/CLIProxyAPI /CLIProxyAPI/CLIProxyAPI
COPY --from=panel-builder /src/dist/index.html /opt/ha/static/management.html
ENV MANAGEMENT_STATIC_PATH=/opt/ha/static HA_PINNED_MANAGEMENT=1
COPY run.sh bootstrap.py nginx.conf /opt/ha/
RUN chmod 755 /opt/ha/run.sh
WORKDIR /data
EXPOSE 8080 8317
ARG BUILD_VERSION=0.1.34
LABEL io.hass.name="CLIProxyAPI" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
