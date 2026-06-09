FROM prefecthq/prefect:2-latest

# Install system dependencies
COPY docker/prefect/install_dependencies.sh .
RUN bash install_dependencies.sh && rm install_dependencies.sh

# Set the entry point to run the application
CMD ["prefect", "server", "start", "--host", "0.0.0.0"]