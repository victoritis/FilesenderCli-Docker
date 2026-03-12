FROM python:3.11-slim

WORKDIR /app

# Install the WEHI FileSenderCli from the bundled source
COPY FileSenderCli/ /filesendercli/
RUN pip install --no-cache-dir /filesendercli/

# Copy the wrapper script (config, ini, and uploads are mounted as volumes)
COPY filesender-wehi--config.py ./

ENTRYPOINT ["python3.11", "filesender-wehi--config.py"]
