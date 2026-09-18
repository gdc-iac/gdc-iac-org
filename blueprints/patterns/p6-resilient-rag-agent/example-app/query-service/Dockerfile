FROM python:3.11-slim

WORKDIR /app
RUN pip install fastapi uvicorn httpx psycopg2-binary pydantic google-auth requests google-cloud-storage python-multipart google-adk==1.27.4

# Create a non-root user
RUN useradd -m -u 1000 appuser

COPY . .

# Switch to non-root user
USER appuser

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
