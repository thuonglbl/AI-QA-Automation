# ----------------------------------------
# Stage 1: Build Frontend (React + Vite)
# ----------------------------------------
FROM node:24-slim AS frontend-builder
WORKDIR /app/frontend

# Copy and install libraries for frontend
COPY frontend/package*.json ./
RUN npm install

# Build UI
COPY frontend/ ./
RUN npm run build
# Build result in folder /app/frontend/dist

# ----------------------------------------
# Stage 2: Build & Run Backend (Final Image)
# ----------------------------------------
FROM python:3.14-slim

RUN pip install uv
WORKDIR /app

# Setup Backend
COPY pyproject.toml uv.lock .python-version README.md ./
COPY src/ ./src/
COPY .env.example .env

# Run uv to install dependencies and create virtual environment
RUN uv sync --no-cache

# KEY: Copy result from Stage 1 to Stage 2
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

# Run app
CMD ["uv", "run", "uvicorn", "src.ai_qa.api:app", "--host", "0.0.0.0", "--port", "8000"]