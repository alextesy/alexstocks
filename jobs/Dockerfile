FROM python:3.11-slim

WORKDIR /app

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files
# NOTE: Build context is project root, not jobs/
COPY jobs/pyproject.toml ./

# Install PyTorch CPU-only first (before other deps to avoid CUDA deps)
# This prevents installation of nvidia-cuda-* packages (~1.5GB+)
RUN uv pip install --system --no-cache \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.2.0,<2.3.0"

# Install remaining dependencies
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy shared code from main app (models, services, config, collectors, repos, templates)
COPY app/db /app/app/db
COPY app/services /app/app/services
COPY app/models /app/app/models
COPY app/repos /app/app/repos
COPY app/collectors /app/app/collectors
COPY app/templates /app/app/templates
COPY app/config.py /app/app/config.py

# Copy job-specific code from jobs/ directory
COPY jobs/ingest /app/ingest
COPY jobs/jobs /app/jobs
COPY jobs/config /app/config

# Set Python path
ENV PYTHONPATH=/app

# Default command (will be overridden in ECS task definition)
CMD ["python", "-c", "print('Specify command in ECS task definition')"]
