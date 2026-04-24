FROM python:3.12-alpine

RUN apk add --no-cache gcc musl-dev libxml2-dev libxslt-dev

WORKDIR /app

COPY src/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ .

CMD ["python3", "/app/main.py"]
