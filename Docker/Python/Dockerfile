# Use official lightweight Python base image
FROM python:3.11-slim

# Silence apt-get output and install git + system deps
RUN apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive apt-get install -qq -y \
    git curl vim less ca-certificates \
    > /dev/null 2>&1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install test dependencies quietly
RUN pip install --no-cache-dir --quiet \
    boto3 \
    pytest \
    requests \
    > /dev/null 2>&1

# Set working directory
WORKDIR /app

# Copy project files (source + tests)
COPY . .

# Default command: run our test runner script
CMD ["python", "run_tests.py"]