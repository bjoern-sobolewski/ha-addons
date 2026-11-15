FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/willxup/cpa-usage-keeper.git \
    && git fetch --depth 1 origin 41b34f12dbef209292765415b860583aad5afc09 \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 41b34f12dbef209292765415b860583aad5afc09
# Maintained viewer, quota analytics, shared names and ranking on the pinned v2 stable source.
COPY patches/ha-v2.patch /tmp/ha-v2.patch
RUN git apply --check /tmp/ha-v2.patch && git apply /tmp/ha-v2.patch

COPY patches/live-stats.patch /tmp/live-stats.patch
RUN git apply --check /tmp/live-stats.patch && git apply /tmp/live-stats.patch

COPY patches/provider-stats.patch /tmp/provider-stats.patch
RUN git apply --check /tmp/provider-stats.patch && git apply /tmp/provider-stats.patch
COPY patches/browser-locale-shared-reset.patch /tmp/browser-locale-shared-reset.patch
RUN git apply --check /tmp/browser-locale-shared-reset.patch && git apply /tmp/browser-locale-shared-reset.patch

COPY patches/quota-policy.patch /tmp/quota-policy.patch
RUN git apply --check /tmp/quota-policy.patch && git apply /tmp/quota-policy.patch
COPY patches/session-rebalance.patch /tmp/session-rebalance.patch
RUN git apply --check /tmp/session-rebalance.patch && git apply /tmp/session-rebalance.patch
COPY patches/live-routing.patch /tmp/live-routing.patch
RUN git apply --check /tmp/live-routing.patch && git apply /tmp/live-routing.patch
COPY patches/email-privacy.patch /tmp/email-privacy.patch
RUN git apply --check /tmp/email-privacy.patch && git apply /tmp/email-privacy.patch
COPY patches/quota-tooltip.patch /tmp/quota-tooltip.patch
RUN git apply --check /tmp/quota-tooltip.patch && git apply /tmp/quota-tooltip.patch
COPY patches/request-previews.patch /tmp/request-previews.patch
RUN git apply --check /tmp/request-previews.patch && git apply /tmp/request-previews.patch
COPY patches/live-routing-layout.patch /tmp/live-routing-layout.patch
RUN git apply --check /tmp/live-routing-layout.patch && git apply /tmp/live-routing-layout.patch

COPY patches/account-errors-reset.patch /tmp/account-errors-reset.patch
RUN git apply --check /tmp/account-errors-reset.patch && git apply /tmp/account-errors-reset.patch

COPY patches/period-ranges.patch /tmp/period-ranges.patch
RUN git apply --check /tmp/period-ranges.patch && git apply /tmp/period-ranges.patch

COPY patches/calendar-test-compat.patch /tmp/calendar-test-compat.patch
RUN git apply --check /tmp/calendar-test-compat.patch && git apply /tmp/calendar-test-compat.patch

COPY patches/upstream-argon-ultra-lite.patch /tmp/upstream-argon-ultra-lite.patch
RUN git apply --check /tmp/upstream-argon-ultra-lite.patch && git apply /tmp/upstream-argon-ultra-lite.patch

COPY patches/upstream-event-capacity.patch /tmp/upstream-event-capacity.patch
RUN git apply --check /tmp/upstream-event-capacity.patch && git apply /tmp/upstream-event-capacity.patch

COPY patches/upstream-stream-compatibility.patch /tmp/upstream-stream-compatibility.patch
RUN git apply --check /tmp/upstream-stream-compatibility.patch && git apply /tmp/upstream-stream-compatibility.patch

FROM node:24-alpine AS web-builder
WORKDIR /src/web
COPY --from=source /src/web/package*.json ./
RUN npm ci
COPY --from=source /src/web/ ./
RUN npm run typecheck && npm run lint && npm test -- --run && npm run build

FROM golang:1.26-alpine AS go-builder
RUN apk add --no-cache build-base
WORKDIR /src
COPY --from=source /src/go.mod /src/go.sum ./
RUN go mod download
COPY --from=source /src/cmd/ ./cmd/
COPY --from=source /src/internal/ ./internal/
COPY --from=source /src/web/static.go ./web/static.go
COPY --from=web-builder /src/web/dist ./web/dist
RUN --mount=type=cache,target=/root/.cache/go-build --mount=type=tmpfs,target=/tmp GIN_MODE=release go test ./internal/...
RUN --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=1 go build -ldflags="-s -w -X cpa-usage-keeper/internal/version.Version=2.1.0-ha.12" -o /out/cpa-usage-keeper ./cmd/server/main.go

FROM ghcr.io/willxup/cpa-usage-keeper:2.1.0@sha256:c071c6326e95601988e011ef38f0fe4cfd2bd50dcebf18848cd10cc1a01edb84
USER root
RUN apk add --no-cache python3 nginx
COPY --from=go-builder /out/cpa-usage-keeper /app/cpa-usage-keeper
COPY --from=source /src/LICENSE /opt/ha/KEEPER-LICENSE
COPY run.sh bootstrap.py nginx.conf viewer-locations.conf /opt/ha/
RUN chmod 755 /opt/ha/run.sh
ENV WORK_DIR=/data TZ=Europe/Berlin
EXPOSE 8082
ARG BUILD_VERSION=0.2.11
LABEL io.hass.name="CPA Usage Keeper" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
