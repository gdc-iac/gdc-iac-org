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
RUN useradd -m -u 1000 appuser

COPY . .

# Switch to non-root user
USER appuser

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
