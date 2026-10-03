FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/CLIProxyAPI.git \
    && git fetch --depth 1 origin 6fecc6e5567912661654a4eaf9b8f5436facd1c2 \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 6fecc6e5567912661654a4eaf9b8f5436facd1c2
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
FROM golang:1.26-bookworm AS builder
WORKDIR /src
COPY --from=source /src/ ./
RUN go test ./internal/quotatraffic ./internal/logging ./internal/refreshdiagnostic ./internal/auth/codex ./sdk/cliproxy/auth ./internal/runtime/executor/helps ./internal/api/handlers/management
RUN CGO_ENABLED=1 go build -buildvcs=false -ldflags="-s -w -X main.Version=8.0.10-ha.5" -o /out/CLIProxyAPI ./cmd/server
FROM alpine:3.20 AS panel-source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/router-for-me/Cli-Proxy-API-Management-Center.git \
    && git fetch --depth 1 origin 752e0ee772220ce49aae1221a3f39f23236590d7 \
    && git checkout --detach FETCH_HEAD
COPY patches/cpamc-key-names.patch /tmp/cpamc-key-names.patch
RUN git apply --check /tmp/cpamc-key-names.patch && git apply /tmp/cpamc-key-names.patch
COPY patches/cpamc-key-layout.patch /tmp/cpamc-key-layout.patch
RUN git apply --check /tmp/cpamc-key-layout.patch && git apply /tmp/cpamc-key-layout.patch
COPY patches/cpamc-auth-errors.patch /tmp/cpamc-auth-errors.patch
RUN git apply --check /tmp/cpamc-auth-errors.patch && git apply /tmp/cpamc-auth-errors.patch
COPY patches/cpamc-native-age.patch /tmp/cpamc-native-age.patch
RUN git apply --check /tmp/cpamc-native-age.patch && git apply /tmp/cpamc-native-age.patch
FROM node:24-alpine AS panel-builder
WORKDIR /src
COPY --from=panel-source /src/ ./
RUN npm install --ignore-scripts && npx --yes --package=bun@1.3.14 bun run verify
FROM eceasy/cli-proxy-api:v8.0.10@sha256:0b007a6abd15aec1f5314908417ceab99f049f75353e3703f52f0968747f6110
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
ARG BUILD_VERSION=0.1.9
LABEL io.hass.name="CLIProxyAPI" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
