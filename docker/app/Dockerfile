FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install system dependencies
COPY docker/app/install_dependencies.sh .
RUN bash install_dependencies.sh && rm install_dependencies.sh

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

# Copy source code
COPY . /app

# Change ownership to non-root user
USER appuser