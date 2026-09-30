FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY . /app

# Expose default port
EXPOSE 8080

# Environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Start the assessment server
CMD ["python3", "server.py"]
