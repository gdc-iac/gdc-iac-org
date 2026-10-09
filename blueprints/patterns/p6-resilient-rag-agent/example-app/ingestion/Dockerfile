FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    boto3 \
    psycopg2-binary==2.9.10 \
    httpx==0.28.1 \
    google-auth \
    "requests>=2.32.3" \
    google-cloud-storage

# Create a non-root user
RUN useradd -m -u 1000 appuser

COPY app.py .

# Switch to non-root user
USER appuser

CMD ["python", "-u", "app.py"]
