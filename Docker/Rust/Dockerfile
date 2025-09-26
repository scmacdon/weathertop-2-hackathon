# Base image: Debian slim for smaller footprint
FROM debian:bullseye-slim

# Install system dependencies, Python, Node.js (LTS), and AWS tools
RUN apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive apt-get install -qq -y \
        python3 \
        python3-venv \
        python3-pip \
        curl \
        git \
        ca-certificates \
        bash \
        gnupg && \
    # Install Node.js (LTS version via NodeSource)
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -qq -y nodejs && \
    # Install Rust
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s - -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up Python virtual environment and install boto3
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir boto3

# Add venv and Node.js binaries to PATH
ENV PATH="/opt/venv/bin:/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy local app files into the container
COPY . .

# Default: Run your test runner script
ENTRYPOINT ["python3", "run_tests.py"]

