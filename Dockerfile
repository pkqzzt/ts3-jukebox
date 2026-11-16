# syntax=docker/dockerfile:1
# Panel image. Build with --target apple to also get gamdl (Apple Music).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /opt/jukebox
COPY jukebox ./jukebox
COPY web ./web
COPY scripts ./scripts
COPY config.example.toml ./
COPY deploy/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --uid 10001 --create-home jukebox \
 && mkdir -p /data/media \
 && chmod +x /usr/local/bin/docker-entrypoint.sh \
 && chown -R jukebox:jukebox /opt/jukebox /data

USER jukebox
EXPOSE 8080 8081
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]


# ---- optional: Apple Music support (gamdl + ffmpeg) -------------------------
FROM base AS apple

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && python3 -m venv /opt/gamdl/venv \
 && /opt/gamdl/venv/bin/pip install --no-cache-dir -U pip "gamdl[widevine]" \
 && rm -rf /var/lib/apt/lists/* \
 && chown -R jukebox:jukebox /opt/gamdl

USER jukebox
ENV GAMDL_BIN=/opt/gamdl/venv/bin/gamdl \
    GAMDL_PY=/opt/gamdl/venv/bin/python
