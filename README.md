# transcribe-ui
User interface for the SUNET transcription service

## Development environment

1. Edit the environment settings, should be in a file named `.env`. The following settings should be sufficient for most cases:
	```env
	API_URL = "http://localhost:8000"
	OIDC_APP_REFRESH_ROUTE = "http://localhost:8000/api/refresh"
	OIDC_APP_LOGIN_ROUTE = "http://localhost:8000/api/login"
	OIDC_APP_LOGOUT_ROUTE = "http://localhost:8000/api/logout"
	```
5. Run the application with uv:
   ```bash
   uv run main.py
   ```
