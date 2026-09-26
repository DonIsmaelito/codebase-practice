# Cold Start — hosted image (InsForge Compute / Fly.io).
#   stage 1 builds the web app; stage 2 is the Python server plus the runtime
#   that generated client codebases (and your terminal) run in, as `runner`.

FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# git + zsh for workspaces and the terminal; tini reaps the many short-lived
# test/terminal processes; `runner` is the unprivileged jail user.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git zsh procps ca-certificates tini less \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /bin/zsh runner \
 && git config --system --add safe.directory '*' \
 && git config --system init.defaultBranch main

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Libraries generated codebases may import (see runtime/requirements.txt).
COPY runtime/requirements.txt runtime/requirements.txt
RUN uv venv /opt/runtime --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/runtime/bin/python -r runtime/requirements.txt

# The server (dependencies first so code changes don't reinstall them).
COPY server/pyproject.toml server/uv.lock server/
RUN cd server && uv sync --frozen --no-install-project
COPY server/ server/
RUN cd server && uv sync --frozen
COPY content/ content/
COPY --from=web /web/dist web/dist

ENV COLDSTART_RUNTIME=/opt/runtime \
    COLDSTART_DATA=/data \
    COLDSTART_HOST=0.0.0.0 \
    COLDSTART_PORT=8080
EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/server/.venv/bin/python", "-m", "coldstart.cli", "serve", "--port", "8080"]
