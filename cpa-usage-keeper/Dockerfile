FROM alpine:3.20 AS source
RUN apk add --no-cache git
WORKDIR /src
RUN git init && git remote add origin https://github.com/willxup/cpa-usage-keeper.git \
    && git fetch --depth 1 origin 3f1b29aa5b0b5284b75ec53573b5146cd50fea1b \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = 3f1b29aa5b0b5284b75ec53573b5146cd50fea1b
COPY patches/viewer-quota.patch /tmp/viewer-quota.patch
RUN git apply --check /tmp/viewer-quota.patch && git apply /tmp/viewer-quota.patch

FROM node:24-alpine AS web-builder
WORKDIR /src/web
COPY --from=source /src/web/package*.json ./
RUN npm ci
COPY --from=source /src/web/ ./
RUN npm run typecheck && npm test -- --run src/pages/test/KeyQuotaPage.test.tsx src/features/key-viewer/test/quotaNavigation.test.tsx && npm run build

FROM golang:1.26-alpine AS go-builder
RUN apk add --no-cache build-base
WORKDIR /src
COPY --from=source /src/go.mod /src/go.sum ./
RUN go mod download
COPY --from=source /src/cmd/ ./cmd/
COPY --from=source /src/internal/ ./internal/
COPY --from=source /src/web/static.go ./web/static.go
COPY --from=web-builder /src/web/dist ./web/dist
RUN go test ./internal/api/test ./internal/config/test
RUN CGO_ENABLED=1 go build -ldflags="-s -w -X cpa-usage-keeper/internal/version.Version=1.15.9-ha.1" -o /out/cpa-usage-keeper ./cmd/server/main.go

FROM ghcr.io/willxup/cpa-usage-keeper:1.15.9@sha256:5a3f3b51f6992fe81756d5d8a0aaaf6765084ff7f612add012ce96291be1eea3
USER root
RUN apk add --no-cache python3 nginx
COPY --from=go-builder /out/cpa-usage-keeper /app/cpa-usage-keeper
COPY --from=source /src/LICENSE /opt/ha/KEEPER-LICENSE
COPY run.sh bootstrap.py nginx.conf viewer-locations.conf /opt/ha/
RUN chmod 755 /opt/ha/run.sh
ENV WORK_DIR=/data TZ=Europe/Berlin
EXPOSE 8082
ARG BUILD_VERSION=0.1.2
LABEL io.hass.name="CPA Usage Keeper" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
