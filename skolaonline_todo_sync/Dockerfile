ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip gcc musl-dev libxml2-dev libxslt-dev

WORKDIR /app

COPY src/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ .

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
