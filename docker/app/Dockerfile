FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
COPY docker/app/install_dependencies.sh .
RUN bash install_dependencies.sh && rm install_dependencies.sh

# Install Python requirements
COPY requirements.txt .
COPY docker/app/install_requirements.sh .
RUN bash install_requirements.sh && rm install_requirements.sh

# Copy source code
COPY src/ ./src/

CMD ["sleep", "infinity"]