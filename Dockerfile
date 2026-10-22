# Reproducible runtime for the CLI. rasterio/pyogrio wheels bundle GDAL, so no system GDAL needed.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY configs ./configs
RUN uv sync --frozen --no-dev
ENV PATH="/opt/venv/bin:$PATH"
ENTRYPOINT ["indus-delta"]
CMD ["--help"]
