# fedtail's web interface in a container: the page on port 8765, the profile in /data.
#
#   docker build -f packaging/docker/Dockerfile -t fedtail .
#   docker run -d --name fedtail -p 127.0.0.1:8765:8765 -v fedtail:/data fedtail
#   docker logs fedtail        # the one-time link (15 minutes); log in on the page
#
# The release puts it on ghcr.io/eugene-vereshchagin/fedtail (CI's `docker` job).
# Everything between the browser and the container is plain HTTP: a TLS proxy or a VPN
# in front of it for anything beyond this computer (docs: the web interface).

FROM python:3.13-slim AS build
COPY . /src
RUN pip wheel --no-cache-dir --no-deps -w /whl /src

FROM python:3.13-slim
LABEL org.opencontainers.image.title="fedtail" \
      org.opencontainers.image.description="fedtail's web interface: the fediverse in a browser tab" \
      org.opencontainers.image.source="https://github.com/eugene-vereshchagin/fedtail" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"
COPY --from=build /whl /whl
# sync between devices and a post's language by its words come along
RUN pip install --no-cache-dir /whl/*.whl "cryptography>=3.4" "langdetect>=1.0.9" \
    && rm -rf /whl \
    && useradd --create-home --uid 1000 fedtail \
    && mkdir /data && chown fedtail /data
COPY packaging/docker/entrypoint.sh /usr/local/bin/fedtail-web
USER fedtail
ENV XDG_CONFIG_HOME=/data/config XDG_DATA_HOME=/data/data XDG_CACHE_HOME=/data/cache \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8765
ENTRYPOINT ["fedtail-web"]
