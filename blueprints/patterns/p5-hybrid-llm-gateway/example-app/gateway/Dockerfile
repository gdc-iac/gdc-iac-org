FROM python:3.11-slim

WORKDIR /app
RUN pip install fastapi uvicorn httpx pydantic google-genai google-auth google-cloud-aiplatform

# Create a non-root user
RUN useradd -m -u 1000 appuser

COPY app.py .

# Switch to non-root user
USER appuser

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
