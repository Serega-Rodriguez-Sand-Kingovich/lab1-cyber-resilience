# syntax=docker/dockerfile:1
# Lab 3: offline smoke-check of the verified Lab 2 classifier.
# Base tag pins the Python patch release and Debian distribution.
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

# Version-pinned runtime libraries only; no Jupyter, pytest, Bandit, or Ruff.
COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN python -m pip install --no-cache-dir -r /app/requirements-runtime.txt

# Copy only the runtime prediction code, the approved model, and its hash reference.
COPY --chown=10001:10001 src/__init__.py src/config.py src/data.py src/inference.py /app/src/
COPY --chown=10001:10001 scripts/docker_smoke.py /app/scripts/docker_smoke.py
COPY --chown=10001:10001 metrics/baseline.json /app/metrics/baseline.json
COPY --chown=10001:10001 models/digits_baseline.joblib /app/models/digits_baseline.joblib

USER 10001:10001
HEALTHCHECK --interval=60s --timeout=20s --retries=3 CMD ["python", "-m", "scripts.docker_smoke"]
CMD ["python", "-m", "scripts.docker_smoke"]
