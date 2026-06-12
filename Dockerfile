FROM docker.io/library/python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python3 -m pip install --break-system-packages --no-cache-dir .

ENTRYPOINT ["smartscan"]
CMD ["--help"]
