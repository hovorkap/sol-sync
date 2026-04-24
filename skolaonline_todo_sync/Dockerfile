ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and build dependencies for lxml/zeep
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-lxml \
    libxml2-dev \
    libxslt-dev \
    gcc \
    musl-dev

WORKDIR /app

COPY src/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ .

COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
