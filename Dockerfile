# syntax=docker/dockerfile:1
# Lab 4: audited non-root FastAPI service on the frozen Lab 2 classifier.
FROM python:3.12.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN groupadd --gid 10001 app && \
    useradd --no-log-init --uid 10001 --gid 10001 --create-home app
COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN python -m pip install --no-cache-dir -r /app/requirements-runtime.txt

COPY --chown=10001:10001 src/__init__.py src/config.py src/data.py src/inference.py src/webapp.py /app/src/
COPY --chown=10001:10001 static/ /app/static/
COPY --chown=10001:10001 scripts/docker_smoke.py scripts/docker_api_smoke.py /app/scripts/
COPY --chown=10001:10001 metrics/baseline.json /app/metrics/baseline.json
COPY --chown=10001:10001 integrity/model.sha256 /app/integrity/model.sha256
COPY --chown=10001:10001 models/digits_baseline.joblib /app/models/digits_baseline.joblib

# Existing Lab 3 SQLite remediation is retained for its known Trivy policy.
RUN set -eu; \
    echo "deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian sid main" > /etc/apt/sources.list.d/lab3-sid.list; \
    printf "Package: *\nPin: release a=unstable\nPin-Priority: -1\n\nPackage: libsqlite3-0\nPin: version 3.54.1-2\nPin-Priority: 1001\n" > /etc/apt/preferences.d/lab3-sqlite; \
    apt-get update -qq; \
    apt-get install -y --no-install-recommends libsqlite3-0=3.54.1-2; \
    test "$(dpkg-query -W -f='${Version}' libsqlite3-0)" = "3.54.1-2"; \
    rm -f /etc/apt/sources.list.d/lab3-sid.list /etc/apt/preferences.d/lab3-sqlite; \
    rm -rf /var/lib/apt/lists/*

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=8s --start-period=15s --retries=3 \
    CMD ["python", "-m", "scripts.docker_api_smoke"]
CMD ["python", "-m", "uvicorn", "src.webapp:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "16", "--timeout-keep-alive", "5", "--no-access-log", "--no-proxy-headers"]
