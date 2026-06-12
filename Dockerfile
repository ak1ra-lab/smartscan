FROM docker.io/library/python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends smartmontools \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN python3 -m pip install --break-system-packages --no-cache-dir .

ENTRYPOINT ["smartscan"]
CMD ["--help"]
