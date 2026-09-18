# Use standard Python slim image for GDC compatibility
FROM python:3.11-slim

# Create a non-root user
RUN groupadd -r gatewayuser && useradd -r -g gatewayuser gatewayuser

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Change ownership to non-root user
RUN chown -R gatewayuser:gatewayuser /app

# Switch to non-root user
USER gatewayuser

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
