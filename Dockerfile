# odcr container image. Choose adapters at build time:
#   docker build -t odcr --build-arg EXTRAS=postgres,sqlserver .
#   docker run --rm -v "$PWD:/work" -w /work --env-file .env odcr run --contract-id orders
FROM python:3.12-slim

ARG EXTRAS=all
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# git: contract repositories from Git; Microsoft ODBC Driver 18: SQL Server / Azure SQL / Synapse / Fabric
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl gnupg \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/odcr
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[${EXTRAS}]"

RUN useradd --create-home --uid 10001 odcr
USER odcr
WORKDIR /work
ENTRYPOINT ["odcr"]
CMD ["--help"]
