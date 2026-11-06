FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/CLIProxyAPI.git \
    && git fetch --depth 1 origin be2563ff74a40979a9aadc59d0b24cedc6ba2e81 \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = be2563ff74a40979a9aadc59d0b24cedc6ba2e81
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
COPY patches/interrupt-test-sync.patch /tmp/interrupt-test-sync.patch
RUN git apply --check /tmp/interrupt-test-sync.patch && git apply /tmp/interrupt-test-sync.patch
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
COPY patches/websocket-test-sync.patch /tmp/websocket-test-sync.patch
RUN git apply --check /tmp/websocket-test-sync.patch && git apply /tmp/websocket-test-sync.patch
COPY patches/quota-observation-compat.patch /tmp/quota-observation-compat.patch
RUN git apply --check /tmp/quota-observation-compat.patch && git apply /tmp/quota-observation-compat.patch
FROM golang:1.26-bookworm AS builder
WORKDIR /src
COPY --from=source /src/go.mod /src/go.sum ./
RUN go mod download
COPY --from=source /src/ ./
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/live ./internal/quotatraffic ./internal/logging ./internal/refreshdiagnostic ./internal/auth/codex ./sdk/cliproxy/auth ./internal/runtime/executor/helps ./internal/api/handlers/management
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/redisqueue ./sdk/cliproxy/usage ./internal/runtime/executor -run "TestCodex|TestUsageQueue"
RUN --mount=type=cache,target=/root/.cache/go-build go test ./sdk/api/handlers/openai
RUN --mount=type=cache,target=/root/.cache/go-build go test ./internal/api -run 'TestManagementV8'
RUN --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=1 go build -buildvcs=false -ldflags="-s -w -X main.Version=8.0.51-main.be2563f-ha.3" -o /out/CLIProxyAPI ./cmd/server
FROM alpine:3.20 AS panel-source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/Cli-Proxy-API-Management-Center.git \
    && git fetch --depth 1 origin f154fa9380825c4fe94bc577a9abaa7e505f8875 \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = f154fa9380825c4fe94bc577a9abaa7e505f8875
COPY patches/cpamc-ha-integration.patch /tmp/cpamc-ha-integration.patch
RUN git apply --check /tmp/cpamc-ha-integration.patch && git apply /tmp/cpamc-ha-integration.patch
COPY patches/cpamc-live-stats.patch /tmp/cpamc-live-stats.patch
RUN git apply --check /tmp/cpamc-live-stats.patch && git apply /tmp/cpamc-live-stats.patch
COPY patches/cpamc-browser-locale-shared-reset.patch /tmp/cpamc-browser-locale-shared-reset.patch
RUN git apply --check /tmp/cpamc-browser-locale-shared-reset.patch && git apply /tmp/cpamc-browser-locale-shared-reset.patch
COPY patches/cpamc-route-recovery.patch /tmp/cpamc-route-recovery.patch
RUN git apply --check /tmp/cpamc-route-recovery.patch && git apply /tmp/cpamc-route-recovery.patch
FROM node:24-alpine AS panel-builder
WORKDIR /src
COPY --from=panel-source /src/package.json /src/bun.lock ./
RUN npx --yes --package=bun@1.4.3 bun install --frozen-lockfile
COPY --from=panel-source /src/ ./
RUN npx --yes --package=bun@1.4.3 bun run verify
FROM eceasy/cli-proxy-api:v8.0.51@sha256:15d13889e1a39a688be306dfbf2f6cf9003e99cd913b5070fa463f8ab2aa0031
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-yaml nginx-light \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /out/CLIProxyAPI /CLIProxyAPI/CLIProxyAPI
COPY --from=panel-builder /src/dist/index.html /opt/ha/static/management.html
ENV MANAGEMENT_STATIC_PATH=/opt/ha/static HA_PINNED_MANAGEMENT=1
COPY run.sh bootstrap.py nginx.conf /opt/ha/
RUN chmod 755 /opt/ha/run.sh
WORKDIR /data
EXPOSE 8080 8317
ARG BUILD_VERSION=0.1.19
LABEL io.hass.name="CLIProxyAPI" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
