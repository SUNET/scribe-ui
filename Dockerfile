FROM ghcr.io/astral-sh/uv:debian

# Copy code
WORKDIR /app
COPY . .

# Expose port
EXPOSE 8888

# Run FastAPI
CMD ["uv", "run", "main.py"]
