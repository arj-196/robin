FROM python:3.12-slim

ARG CODEX_VERSION=0.128.0
ARG GIT_USER_NAME="Robin Auto Coder"
ARG GIT_USER_EMAIL="auto-coder@arj-crew.com"
ARG AUTO_CODER_GITHUB_SSH_PRIVATE_KEY=""
ARG AUTO_CODER_GITHUB_SSH_PUBLIC_KEY=""

ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/tmp/robin-uv-env
ENV AUTO_CODER_CODEX_SANDBOX=danger-full-access

RUN apt-get update \
  && apt-get install -y --no-install-recommends git nodejs npm ca-certificates openssh-client \
  && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
  "loguru>=0.7.3,<1.0.0" \
  "typer>=0.20.0,<1.0.0" \
  "uv>=0.9.0,<1.0.0"

RUN npm install -g "@openai/codex@${CODEX_VERSION}"

RUN git config --global user.name "${GIT_USER_NAME}" \
  && git config --global user.email "${GIT_USER_EMAIL}" \
  && git config --global init.defaultBranch main \
  && git config --global --add safe.directory '*'

# add ssh keys for github access
RUN mkdir -p /root/.ssh \
  && printf "%b" "${AUTO_CODER_GITHUB_SSH_PRIVATE_KEY}" > /root/.ssh/id_ed25519 \
  && printf "%s\n" "${AUTO_CODER_GITHUB_SSH_PUBLIC_KEY}" > /root/.ssh/id_ed25519.pub

RUN chmod 700 /root/.ssh \
  && chmod 600 /root/.ssh/id_ed25519 \
  && chmod 644 /root/.ssh/id_ed25519.pub \
  && ssh-keyscan -H github.com >> /root/.ssh/known_hosts \
  && chmod 644 /root/.ssh/known_hosts

USER root

WORKDIR /workspace
