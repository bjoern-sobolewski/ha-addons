FROM ghcr.io/willxup/cpa-usage-keeper:1.15.9@sha256:5a3f3b51f6992fe81756d5d8a0aaaf6765084ff7f612add012ce96291be1eea3
USER root
RUN apk add --no-cache python3
COPY run.sh bootstrap.py /opt/ha/
RUN chmod 755 /opt/ha/run.sh
ENV WORK_DIR=/data TZ=Europe/Berlin
ARG BUILD_VERSION=0.1.0
LABEL io.hass.name="CPA Usage Keeper" io.hass.type="addon" io.hass.arch="aarch64|amd64" io.hass.version="${BUILD_VERSION}"
ENTRYPOINT ["/opt/ha/run.sh"]
CMD []
