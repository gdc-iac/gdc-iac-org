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

FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi==0.142.2 \
    starlette==1.7.0 \
    uvicorn==0.34.0 \
    httpx==0.28.1 \
    psycopg2-binary==2.9.10 \
    pydantic==2.11.1 \
    google-auth \
    "requests>=2.32.3" \
    google-cloud-storage \
    python-multipart==0.0.31 \
    "PyJWT[crypto]>=2.10.1"

# Create a non-root user
RUN groupadd -g 1000 appuser && useradd -m -u 1000 -g 1000 appuser

COPY . .

# Switch to explicit numeric non-root user
USER 1000:1000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
