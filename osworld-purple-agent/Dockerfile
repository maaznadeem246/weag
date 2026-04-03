FROM python:3.11-slim

WORKDIR /app

# Copy project manifest and source first to leverage Docker layer cache.
COPY pyproject.toml .
COPY src/ ./src/

# Install the package and its dependencies.
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
