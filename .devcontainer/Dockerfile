# Spark 4.1 requires Java 17/21 and Python 3.10+
FROM python:3.12-slim-bookworm

ARG SPARK_VERSION=4.1.3
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless git curl ca-certificates make procps sudo openssh-client \
    # arch-independent JAVA_HOME
    && ln -sfn "$(dirname "$(dirname "$(readlink -f "$(which java)")")")" /usr/lib/jvm/default-java \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/default-java

# Non-root user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m -s /bin/bash $USERNAME \
    && echo "$USERNAME ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && mkdir -p /opt/venv && chown -R $USERNAME:$USERNAME /opt/venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

USER $USERNAME

# Spark + tooling in a shared venv (the project's workspace packages are installed on create)
RUN uv venv /opt/venv --python 3.12 \
    && uv pip install \
        "pyspark[connect]==${SPARK_VERSION}" \
        pytest pytest-cov chispa ruff mypy ipykernel jupyterlab pandas pyarrow

ENV SPARK_HOME=/opt/venv/lib/python3.12/site-packages/pyspark \
    PYSPARK_PYTHON=/opt/venv/bin/python \
    PYSPARK_DRIVER_PYTHON=/opt/venv/bin/python \
    PATH=/opt/venv/lib/python3.12/site-packages/pyspark/bin:$PATH

WORKDIR /workspaces/dataops
