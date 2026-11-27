# odcr container image: odcr and the drivers for every platform, ready for pipeline jobs.
#
#   docker run --rm -v "$PWD:/work" --env-file .env ghcr.io/sulfibashy/odcr odcr run --contract-id orders
#
# Published to ghcr.io/sulfibashy/odcr for linux/amd64 and linux/arm64 on every release.
# Build your own, with only the adapters you need:
#   docker build -t odcr --build-arg EXTRAS=postgres,sqlserver .                 # from this checkout
#   docker build -t odcr --build-arg ODCR_VERSION=0.2.2 .                        # a release from PyPI
FROM python:3.12-slim

ARG EXTRAS=all
ARG ODCR_VERSION=
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

LABEL org.opencontainers.image.title="odcr" \
      org.opencontainers.image.description="Open Data Contract Runtime: enforce ODCS data contracts where data lands" \
      org.opencontainers.image.source="https://github.com/sulfibashy/odcr" \
      org.opencontainers.image.documentation="https://sulfibashy.github.io/odcr/" \
      org.opencontainers.image.licenses="Apache-2.0"

# git: contract repositories in Git. Microsoft ODBC Driver 18: SQL Server, Azure SQL, Synapse, Fabric with
# Entra ID (without it, odcr falls back to the pure-Python pytds client).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl gnupg unixodbc \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql.list \
 && apt-get update \
 && (ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 || echo "ODBC Driver 18 not available for ${TARGETARCH}") \
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/odcr
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# IBM Db2 (ibm_db) has no ARM64 Linux driver, so it is added on amd64 only.
RUN set -e; extras="${EXTRAS}"; \
    if [ "${EXTRAS}" = "all" ] && [ "${TARGETARCH:-amd64}" = "amd64" ]; then extras="all,db2"; fi; \
    if [ -n "${ODCR_VERSION}" ]; then pip install "odcr[${extras}]==${ODCR_VERSION}"; else pip install ".[${extras}]"; fi; \
    rm -rf /opt/odcr/src; chmod +x /usr/local/bin/docker-entrypoint.sh; odcr --version

RUN useradd --create-home --uid 10001 odcr
USER odcr
WORKDIR /work
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["odcr", "--help"]
