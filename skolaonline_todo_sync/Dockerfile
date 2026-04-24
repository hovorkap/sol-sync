FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-lxml \
    gcc \
    musl-dev \
    libxml2-dev \
    libxslt-dev

COPY src/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# COPY --chmod ensures files are world-readable regardless of umask or
# Docker layer caching, bypassing the HA non-root user permission issue.
COPY --chmod=755 src/ /app/

ENTRYPOINT ["python3", "/app/main.py"]
