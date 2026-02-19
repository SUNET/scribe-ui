# scribe-ui

User interface built on NiceGUI for the SUNET transcription service (Sunet Scribe).

## Features

- **Transcription Interface**: Upload and manage audio/video transcription jobs
- **Real-time Updates**: Live job status tracking and notifications
- **User Dashboard**: View and manage transcription history
- **OIDC Authentication**: Secure login via OpenID Connect
- **Redis Storage**: Optional Redis backend for session storage

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (recommended package manager)
- Redis (recommended for production)

## Development Environment Setup

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd scribe-ui
uv sync
```

### 2. Configure Environment Variables

Create a `.env` file in the project root with the following settings:

```env
# API configuration
API_URL="http://localhost:8000"

# OIDC configuration
OIDC_APP_REFRESH_ROUTE="http://localhost:8000/api/refresh"
OIDC_APP_LOGIN_ROUTE="http://localhost:8000/api/login"
OIDC_APP_LOGOUT_ROUTE="http://localhost:8000/api/logout"

# Storage configuration
STORAGE_SECRET="your-secret-key"
NICEGUI_REDIS_URL="redis://localhost:6379"  # Optional: Redis storage URL
```

### 3. Run the Application

```bash
uv run main.py
```

The application will be available at `http://localhost:8888`.

## Redis Storage (Recommended)

Using NiceGUI together with Redis is recommended to avoid having user data written to disk. This project includes `nicegui[redis]` as a dependency.

To run a Redis instance without persistent data storage:

```bash
docker run -d -p 6379:6379 redis redis-server --save ''
```

## Docker

Build and run with Docker:

```bash
docker build -t scribe-ui .
docker run -p 8888:8888 --env-file .env scribe-ui
```

## Testing

Run tests with pytest:

```bash
uv run pytest
```

## Project Structure

```
scribe-ui/
├── main.py             # NiceGUI application entry point
├── components/         # Reusable UI components
├── pages/              # Page definitions
├── db/                 # Database operations
├── utils/              # Utilities and settings
├── static/             # Static assets
└── tests/              # Test files
```

## License

See [LICENSE](LICENSE) for details.
