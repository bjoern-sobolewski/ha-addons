FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/CLIProxyAPI.git \
    && git fetch --depth 1 origin 0d18d3b365be000eeaee7de4615f9da596b2059d \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 0d18d3b365be000eeaee7de4615f9da596b2059d
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
FROM golang:1.26-bookworm AS builder
WORKDIR /src
COPY --from=source /src/ ./
RUN go test ./internal/quotatraffic ./internal/logging ./internal/refreshdiagnostic ./internal/auth/codex ./sdk/cliproxy/auth ./internal/runtime/executor/helps ./internal/api/handlers/management
RUN go test ./internal/redisqueue ./sdk/cliproxy/usage ./internal/runtime/executor -run "TestCodex|TestUsageQueue"
RUN go test ./sdk/api/handlers/openai
RUN CGO_ENABLED=1 go build -buildvcs=false -ldflags="-s -w -X main.Version=8.0.28-ha.2" -o /out/CLIProxyAPI ./cmd/server
FROM alpine:3.20 AS panel-source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/Cli-Proxy-API-Management-Center.git \
    && git fetch --depth 1 origin e5c7694b096a37c7555365a9089b14b8166ce74b \
    && git checkout --detach FETCH_HEAD
COPY patches/cpamc-key-names.patch /tmp/cpamc-key-names.patch
RUN git apply --check /tmp/cpamc-key-names.patch && git apply /tmp/cpamc-key-names.patch
COPY patches/cpamc-auth-errors.patch /tmp/cpamc-auth-errors.patch
RUN git apply --check /tmp/cpamc-auth-errors.patch && git apply /tmp/cpamc-auth-errors.patch
COPY patches/cpamc-native-age.patch /tmp/cpamc-native-age.patch
RUN git apply --check /tmp/cpamc-native-age.patch && git apply /tmp/cpamc-native-age.patch
COPY patches/cpamc-traffic-native.patch /tmp/cpamc-traffic-native.patch
RUN git apply --check /tmp/cpamc-traffic-native.patch && git apply /tmp/cpamc-traffic-native.patch
COPY patches/cpamc-upstream-compatibility.patch /tmp/cpamc-upstream-compatibility.patch
RUN git apply --check /tmp/cpamc-upstream-compatibility.patch && git apply /tmp/cpamc-upstream-compatibility.patch
FROM node:24-alpine AS panel-builder
WORKDIR /src
COPY --from=panel-source /src/ ./
# 6.13.0 imports an undeclared @codemirror/streamparser dependency. Keep the
# previously verified language release until upstream fixes its package.
RUN npx --yes --package=bun@1.3.14 bun install --frozen-lockfile \
    && npx --yes --package=bun@1.3.14 bun run verify
FROM eceasy/cli-proxy-api:v8.0.28@sha256:5de1679350c368fb031d46900da30d97c1e9e9a3b150fc4c4181e7e65022a09e
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
ARG BUILD_VERSION=0.1.15
LABEL io.hass.name="CLIProxyAPI" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
