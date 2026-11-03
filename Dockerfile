FROM python:3.12-alpine3.22

LABEL org.opencontainers.image.source="https://github.com/tklein1801/concourse-ssh-scp-resource" \
      org.opencontainers.image.url="https://github.com/tklein1801/concourse-ssh-scp-resource" \
      org.opencontainers.image.title="concourse-ssh-scp-resource" \
      org.opencontainers.image.description="A Concourse resource to run commands on hosts or copy files using SSH or SCP."

RUN apk add --no-cache openssh

COPY src/* /opt/resource/
COPY tests/ /opt/resource/tests/
