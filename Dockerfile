FROM python:3.12-alpine3.22

RUN apk add --no-cache openssh

COPY src/* /opt/resource/
COPY tests/ /opt/resource/tests/
