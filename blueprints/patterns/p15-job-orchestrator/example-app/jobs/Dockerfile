# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get dist-upgrade -y && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade "pip>=25.1" "setuptools>=78.1.1" "wheel>=0.45.1" && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends ca-certificates && \
    (pip uninstall -y setuptools wheel || true) && \
    rm -rf /usr/local/lib/python3.11/ensurepip \
           /usr/lib/python3/dist-packages/setuptools* \
           /usr/local/lib/python3.11/site-packages/setuptools* \
           /usr/local/lib/python3.11/site-packages/wheel* \
           /usr/local/lib/python3.11/site-packages/pip* \
           /usr/local/bin/pip* \
           /usr/local/lib/python3.11/site-packages/distutils-precedence.pth \
           /var/lib/apt/lists/* && \
    groupadd -g 65532 nonroot && \
    useradd -u 65532 -g 65532 -d /home/appuser -m -s /usr/sbin/nologin nonroot

COPY --from=builder /install /usr/local
COPY common ./common
COPY p15_jobs ./p15_jobs

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/home/appuser

RUN python3 -c "import psycopg2, boto3, httpx, cryptography; print('RUNTIME_IMPORTS_OK')"

USER 65532:65532

ENTRYPOINT ["python", "-m", "p15_jobs.runner"]
