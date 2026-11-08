FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/willxup/cpa-usage-keeper.git \
    && git fetch --depth 1 origin 7b2b670f631335c0e2223af769c5abc04d731d8a \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 7b2b670f631335c0e2223af769c5abc04d731d8a
# Maintained viewer, quota analytics, shared names and ranking on the frozen v2 main tree.
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
RUN --mount=type=cache,target=/root/.cache/go-build --mount=type=tmpfs,target=/tmp go test ./internal/...
RUN --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=1 go build -ldflags="-s -w -X cpa-usage-keeper/internal/version.Version=2.0.3-main.7b2b670-ha.8" -o /out/cpa-usage-keeper ./cmd/server/main.go

FROM ghcr.io/willxup/cpa-usage-keeper:2.0.3@sha256:e56daad41fea07eff80045b0efb41f4c80f092ab3e87090a4089e0446cfe6855
USER root
RUN apk add --no-cache python3 nginx
COPY --from=go-builder /out/cpa-usage-keeper /app/cpa-usage-keeper
COPY --from=source /src/LICENSE /opt/ha/KEEPER-LICENSE
COPY run.sh bootstrap.py nginx.conf viewer-locations.conf /opt/ha/
RUN chmod 755 /opt/ha/run.sh
ENV WORK_DIR=/data TZ=Europe/Berlin
EXPOSE 8082
ARG BUILD_VERSION=0.2.7
LABEL io.hass.name="CPA Usage Keeper" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
