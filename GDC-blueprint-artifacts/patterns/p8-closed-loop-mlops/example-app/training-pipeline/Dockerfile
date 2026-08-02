FROM python:3.11-slim

WORKDIR /app
RUN pip install boto3 google-cloud-storage

# Create a non-root user
RUN useradd -m -u 1000 appuser

COPY app.py .

# Switch to non-root user
USER appuser

CMD ["python", "-u", "app.py"]
