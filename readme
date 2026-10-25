# WOT Tournaments

WOT Tournaments is a full-stack app for organizing and managing Wargaming.net tournaments. The project combines a FastAPI backend, a React frontend, PostgreSQL, and Docker-based deployment. Users can register, authenticate, connect a Wargaming account, create tournaments, track participation, and view tournament statistics.

## What is included

- FastAPI backend for tournament logic and API endpoints
- PostgreSQL database for persistent data
- React + Vite frontend for tournament management
- Docker Compose deployment configuration
- Adminer for database inspection in development

## Deployment architecture

The project runs as several containers:

- backend — FastAPI application with API on port 8000
- frontend — production React build served via Nginx on port 80
- postgres — PostgreSQL database
- adminer — database administration UI on port 8080

The frontend is served through Nginx and proxies API requests to the backend service. This allows the application to be used at a single entry point: http://localhost.

## Environment setup

1. Copy .env.example to .env.
2. Fill in the required values:
   - POSTGRES_USER
   - POSTGRES_PASSWORD
   - POSTGRES_DB
   - DATABASE_URL
   - SECRET_KEY
   - ALGORITHM
   - ACCESS_TOKEN_EXPIRE_MINUTES
   - WG_APP_ID
   - WG_REDIRECT_URI
   - FRONTEND_HOST
3. Make sure the Wargaming callback URL matches the deployed host. For local deployment it is usually:
   - http://localhost/api/v1/auth/wargaming/callback

## Run with Docker Compose

From the project root, run:

```bash
docker compose up --build -d
```

After the containers start:

- Frontend: http://localhost
- Backend API: http://localhost:8000
- API docs: http://localhost/docs
- Adminer: http://localhost:8080

To stop the environment:

```bash
docker compose down
```

To rebuild after code changes:

```bash
docker compose up --build -d
```

## Development notes

If you want to run the frontend in development mode manually, use:

```bash
cd frontend
npm install
npm run dev
```

The development server proxies /api requests to the backend at http://127.0.0.1:8000.

For production deployment, prefer the Docker Compose flow above because it builds and serves the production frontend bundle.

## Wargaming integration

The backend also supports authentication with Wargaming.net. Before enabling this flow, set valid WG API values in .env and make sure the redirect URI is registered in the Wargaming app settings.

The application stores encrypted Wargaming access tokens and requires a stable SECRET_KEY for existing users. If tokens were already saved in the database, keep the same secret when migrating or redeploying.

## Project overview

This project is designed for organizing tournaments with Wargaming account validation, battle statistics tracking, and automatic update logic while a tournament is active. It is intended for local development and deployment in a Dockerized environment, with a simple path to production-style hosting using Nginx and PostgreSQL.