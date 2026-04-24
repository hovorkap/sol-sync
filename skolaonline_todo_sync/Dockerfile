FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-lxml \
    gcc \
    musl-dev \
    libxml2-dev \
    libxslt-dev

WORKDIR /app

COPY src/requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY src/ .

ENTRYPOINT ["python3", "/app/main.py"]
