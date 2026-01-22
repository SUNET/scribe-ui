# transcribe-ui
User interface for the SUNET transcription service

## Requirements

- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Redis (recommended for production)

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd transcribe-ui
   ```

2. Install dependencies using uv:
   ```bash
   uv sync
   ```

3. Create a `.env` file with your environment settings:
   ```env
   API_URL = "http://localhost:8000"
   OIDC_APP_REFRESH_ROUTE = "http://localhost:8000/api/refresh"
   OIDC_APP_LOGIN_ROUTE = "http://localhost:8000/api/login"
   OIDC_APP_LOGOUT_ROUTE = "http://localhost:8000/api/logout"
   STORAGE_SECRET = "your-secret-key"
   ```

## Running the Application

### Development

Run the application locally with uv:
```bash
uv run main.py
```

The application will be available at `http://localhost:8888`.

### Docker

Build and run using Docker:
```bash
docker build -t transcribe-ui .
docker run -p 8888:8888 --env-file .env transcribe-ui
```

## Redis Storage (Recommended)

Using NiceGUI together with Redis is recommended to avoid having user data written to disk. This project includes `nicegui[redis]` as a dependency.

To enable Redis storage:

1. Run a Redis instance (e.g., using Docker):
   ```bash
   docker run -d -p 6379:6379 redis
   ```

2. Set the `NICEGUI_STORAGE` environment variable:
   ```env
   NICEGUI_STORAGE = "redis://localhost:6379"
   ```

## Running Tests

```bash
uv run pytest
```
