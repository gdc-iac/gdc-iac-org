FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi==0.142.2 \
    starlette==1.7.0 \
    uvicorn==0.34.0 \
    httpx==0.28.1 \
    pydantic==2.11.1 \
    google-genai \
    google-auth \
    google-cloud-aiplatform

# Create a non-root user
RUN useradd -m -u 1000 appuser

COPY app.py .

# Switch to non-root user
USER appuser

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
