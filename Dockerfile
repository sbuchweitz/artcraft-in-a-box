# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.13-alpine
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.31-alpine

# Stage 1: download the pinned release zips (verified against apps.json), unpack and prune them,
# render the landing page, gzip the big files. The output is plain files, identical for every
# platform, so this stage always runs natively on the build host.
FROM --platform=$BUILDPLATFORM ${PYTHON_IMAGE} AS site
WORKDIR /src
COPY tools/ tools/
COPY site/ site/
COPY apps.json ./
RUN --mount=type=cache,target=/cache,id=artcraft-downloads \
    PYTHONPATH=tools python -m artbox.build --manifest apps.json --site site --cache /cache --out /out

# Stage 2: nginx as non-root on port 8080. No RUN steps, so multi-arch builds need no emulation.
FROM ${NGINX_IMAGE}
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=site /out /usr/share/nginx/artcraft
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
