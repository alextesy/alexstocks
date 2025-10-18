FROM python:3.11-slim

WORKDIR /app

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files
# NOTE: Build context is project root, not jobs/
COPY jobs/pyproject.toml ./

# Install dependencies
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy shared code from main app (models, services, config, collectors)
COPY app/db /app/app/db
COPY app/services /app/app/services
COPY app/models /app/app/models
COPY app/collectors /app/app/collectors
COPY app/config.py /app/app/config.py

# Copy job-specific code from jobs/ directory
COPY jobs/ingest /app/ingest
COPY jobs/jobs /app/jobs

# Set Python path
ENV PYTHONPATH=/app

# Default command (will be overridden in ECS task definition)
CMD ["python", "-c", "print('Specify command in ECS task definition')"]
