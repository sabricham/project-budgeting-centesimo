FROM python:3.12-slim

# openssl serve solo a generare il certificato self-signed di sviluppo (§1.4).
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8443

ENTRYPOINT ["/app/entrypoint.sh"]
