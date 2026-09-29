FROM python:3.12-slim AS builder
WORKDIR /build
# Cache-friendly order: copy only the dependency manifest first so the
# (slow) dependency install layer is reused until pyproject.toml changes.
COPY pyproject.toml .
# Install ONLY the declared third-party dependencies, not the local
# `civicpulse-backend` package. The application source is copied into the
# final stage below; installing the package here would require the `app`
# directory to exist in the builder and would bust the dependency cache on
# every source change (it previously failed the build outright with
# "package directory 'app' does not exist").
# The optional `test` extras are included because the image runs the suite
# (docker compose exec backend pytest ...) and CI runs the same suite.
RUN pip install --no-cache-dir --prefix=/install \
    $(python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb')); print(' '.join(d['project']['dependencies'] + d['project']['optional-dependencies']['test']))")

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
