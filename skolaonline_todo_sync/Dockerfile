FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-lxml \
    gcc \
    musl-dev \
    libxml2-dev \
    libxslt-dev

# Copy source into a temporary build directory (avoids /app permission issues
# when HA runs the container as a non-root user).
COPY src/ /tmp/app-src/

RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/app-src/requirements.txt

# Install sibling modules into site-packages so they're importable from anywhere.
RUN SITE=$(python3 -c "import site; print(site.getsitepackages()[0])") && \
    cp /tmp/app-src/skolaonline.py \
       /tmp/app-src/icloud_reminders.py \
       /tmp/app-src/sync.py \
       "$SITE/"

# Install main entry point to a world-executable location.
RUN cp /tmp/app-src/main.py /usr/local/bin/sol-sync && \
    chmod 755 /usr/local/bin/sol-sync

ENTRYPOINT ["python3", "/usr/local/bin/sol-sync"]
