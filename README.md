# transcribe-ui
User interface for the SUNET transcription service

## Features

### Admin Dashboard
The admin dashboard provides comprehensive management capabilities including:
- **Group Management**: Create and manage user groups with transcription quotas
- **User Management**: Enable/disable users and assign admin roles
- **Customer Management**: View and manage customer accounts
- **Price Plan Display**: View current price plan and remaining blocks (for fixed plans)
  - Shows plan name and type
  - Displays blocks remaining with visual progress indicator
  - Color-coded warnings when blocks are running low
- **Statistics**: View detailed transcription statistics per group and user
- **Health Monitoring**: Monitor system health and worker status (BOFH users only)

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
