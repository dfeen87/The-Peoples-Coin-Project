# The People's Coin — Backend & System Controller

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-2.2.5-green.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL 15](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)

**Stack:** Python (Flask), PostgreSQL 15, SQLAlchemy, Docker  
**Status:** Working backend · Structure stabilized · Live site currently non-functional

---

## Table of Contents

- [Disclaimer](#disclaimer)
- [Project Overview](#project-overview)
- [System Controller](#system-controller)
- [What You Can Build](#what-you-can-build-with-this-backend-today)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Application](#running-the-application)
- [Architecture & Components](#architecture--components)
- [API Documentation](#api-documentation)
- [Global Observability Node](#global-observability-node)
- [Kubernetes Integration](#kubernetes-integration)
- [Monitoring & Logging](#monitoring--logging)
- [Testing](#testing)
- [Biological Inspiration](#biological-inspiration)
- [Technologies & Tools](#technologies--tools)
- [Benefits of Cloning This Repository](#benefits-of-cloning-this-repository)
- [Development & Production Readiness](#development--production-readiness)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)
- [Supporting the Project](#supporting-the-project)
- [Acknowledgements](#acknowledgements)
- [About](#about)

---

## Disclaimer
> ⚠️ **IMPORTANT NOTE:** NOT AFFILIATED WITH ANY CRYPTO COINS. This project does not mint coins that are sold.

The live site is currently non-functional.

Any keys, credentials, or configuration values present in this repository are illustrative only and must not be used for operational or production purposes.

## Project Overview

The People's Coin backend serves as the resilient core of the platform, responsible for securely recording, validating, and managing acts of goodwill contributed by users across a global network.

The system is built on PostgreSQL 15 for durable, scalable data storage and exposes a RESTful Flask API for managing:

- **User accounts and wallets** — Secure authentication and balance tracking
- **Goodwill actions and balances** — Recording and validating acts of kindness
- **Proposals and governance workflows** — Democratic decision-making processes
- **Council membership and oversight structures** — Leadership and accountability

Every interaction is validated, persistently stored, and made available for auditing, ensuring transparency, integrity, and long-term reliability as system load increases.

## System Controller

At the center of the backend is the System Controller, an intelligent orchestration layer designed to monitor and adapt backend behavior based on real-world conditions.

The controller continuously observes:

- CPU utilization
- Memory usage
- Disk availability
- Task queue depth (when available)

It analyzes both real-time metrics and historical workload data stored in the database to generate data-driven recommendations. These recommendations may include adjusting background worker counts or scaling deployment replicas when running in a containerized environment.

All recommendations and actions are recorded, enabling traceability and post-hoc analysis.

---

## What You Can Build With This Backend Today

This backend is intentionally generic and modular. It can be used immediately as:

- **A governance and voting backend** for communities, DAOs, or cooperatives (proposals, councils, decision tracking)
- **A contribution or reputation ledger** to record, score, and audit non-financial actions (volunteer work, moderation, civic engagement)
- **A backend template for civic or nonprofit platforms** requiring transparency, auditability, and long-term data integrity
- **A system orchestration experiment** demonstrating intelligent resource monitoring and adaptive scaling via a centralized controller
- **A research platform** for studying incentive alignment, governance dynamics, and system resilience under load
- **A foundation for tokenized or non-tokenized reward systems**, independent of any specific blockchain or frontend

The system is designed to run locally, in containers, or in cloud environments, with optional Redis and Kubernetes integration depending on deployment needs.

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+** — [Download Python](https://www.python.org/downloads/)
- **PostgreSQL 15+** — [Download PostgreSQL](https://www.postgresql.org/download/)
- **Docker & Docker Compose** (optional, for containerized deployment) — [Get Docker](https://docs.docker.com/get-docker/)
- **Redis** (optional, for task queuing) — [Redis Documentation](https://redis.io/docs/getting-started/)
- **Git** — For cloning the repository

---

## Getting Started

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/dfeen87/the-peoples-coin-project.git
   cd the-peoples-coin-project
   ```

2. **Create and activate a Python virtual environment**
   ```bash
   # On macOS/Linux
   python3 -m venv venv
   source venv/bin/activate

   # On Windows
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up PostgreSQL database**
   ```bash
   # Create a new database
   createdb peoples_coin

   # Or using PostgreSQL CLI
   psql -U postgres -c "CREATE DATABASE peoples_coin;"
   ```

5. **Initialize database migrations**
   ```bash
   flask db upgrade
   # Or using the manage script
   python manage.py db upgrade
   ```

### Environment Variables

Create a `.env` file in the project root with the following configuration:

#### Required Variables

```bash
# Database Configuration
DATABASE_URL=postgresql://username:password@localhost:5432/peoples_coin
DB_USER=your_db_user
DB_PASS=your_db_password
DB_NAME=peoples_coin

# Flask Configuration
FLASK_APP=peoples_coin
FLASK_ENV=development
SECRET_KEY=your-secret-key-here

# Security
RECAPTCHA_SITE_KEY=your_recaptcha_site_key
RECAPTCHA_SECRET_KEY=your_recaptcha_secret_key
```

#### Optional Variables

```bash
# Redis (for task queuing and caching)
CELERY_BROKER_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0

# Observability Node
OBSERVABILITY_PORT=8080
OBSERVABILITY_HOST=0.0.0.0

# Kubernetes (for auto-scaling)
KUBERNETES_NAMESPACE=default
KUBERNETES_DEPLOYMENT_NAME=peoples-coin-backend
MIN_REPLICAS=1
MAX_REPLICAS=10

# Google Cloud (if using Cloud Run or Firebase)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
INSTANCE_CONNECTION_NAME=project:region:instance

# RabbitMQ (alternative to Redis)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

### Running the Application

#### Option 1: Local Development

```bash
# Run the Flask API server
flask run --host=0.0.0.0 --port=8080

# Or using the app directly
python peoples_coin/app.py

# In a separate terminal, run the System Controller (optional)
python peoples_coin/start_background.py
```

#### Option 2: Using Docker Compose

```bash
# Build and start all services
docker-compose up --build

# Run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

The API will be available at `http://localhost:8080`

#### Option 3: Run Observability Node Separately

**Important:** Configure a different port when running alongside the main API to avoid conflicts:

```bash
# The observability node uses port 8080 by default
# Change this if the main API is also using port 8080
export OBSERVABILITY_PORT=8081

# Start the observability node for monitoring
python -m observability_node.run

# Or
cd observability_node
python app.py
```

The observability node will be available at the configured port (e.g., `http://localhost:8081`).

---

## Architecture & Components

The backend follows a modular, fault-tolerant design:

### SQLAlchemy ORM

- UUID primary keys
- ENUM-based status modeling
- JSONB fields for flexible contextual data
- Timestamp triggers for reliable audit metadata

### Flask REST API

- Clear separation between application bootstrapping and domain logic
- Modular routes and services for extensibility

### Asynchronous Processing

- Background workers for non-blocking task execution
- Optional Redis integration for queue management
- Celery support for distributed task processing
- RabbitMQ integration for message queuing

### Auditing & Observability

- Controller decisions are logged to a dedicated database table
- System logs complement persistent audit records
- Comprehensive audit trails for all user actions
- Real-time monitoring through the Observability Node

---

## API Documentation

The People's Coin backend uses **Flasgger** for automatic API documentation generation.

### Accessing API Docs

Once the application is running, you can access the interactive API documentation at:

```
http://localhost:8080/apidocs
```

The Swagger UI provides:
- **Interactive API testing** — Try out endpoints directly from the browser
- **Request/Response schemas** — See exactly what data structures are expected
- **Authentication flows** — Test secured endpoints with API keys
- **Model definitions** — Explore database models and their relationships

### Key API Endpoints

The backend exposes several categorized endpoint groups:

- **Authentication** (`/auth/*`) — User login, registration, and session management
- **User Management** (`/api/users/*`) — User profiles and account operations
- **Goodwill Actions** (`/api/goodwill/*`) — Submit and track acts of kindness
- **Governance** (`/api/governance/*`) — Proposals, voting, and council operations
- **Blockchain** (`/api/blockchain/*`) — Chain validation and block management
- **Metabolic System** (`/api/metabolic/*`) — Resource allocation and system health
- **Immune System** (`/api/immune/*`) — Content moderation and reporting
- **Status & Health** (`/status/*`) — System health checks and monitoring

For detailed endpoint documentation, refer to the Swagger UI after starting the server.

---

## Global Observability Node

The Global Observability Node is a lightweight, read-only REST API that provides safe, non-intrusive access to internal system state. This observability layer enables external monitoring without affecting system behavior.

### Key Features

- **Read-Only Access**: All endpoints are GET-only. POST, PUT, PATCH, and DELETE requests are rejected with 405 Method Not Allowed.
- **Safe Monitoring**: No write operations, no database modifications, no controller actions triggered.
- **Independent Operation**: Can run as a standalone service (configure port to avoid conflicts with main API).
- **Thread-Safe**: Uses read-only database queries and snapshot-based metrics.

### Endpoints

#### 1. GET /health
Returns basic service liveness, uptime, and version information.

#### 2. GET /api/system_state
Returns comprehensive system metrics including CPU, memory, disk, database activity, Redis queue depth, Kubernetes status, and last controller evaluation.

#### 3. GET /api/controller_decisions
Returns recent controller decisions, scaling recommendations, and actions taken.

#### 4. GET /api/governance_state
Returns high-level governance metadata including proposal counts, vote totals, and council membership.

#### 5. GET /api/audit_summary
Returns recent audit log entries including event types, timestamps, and context.

### Quick Start

```bash
# Set required environment variables
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
export OBSERVABILITY_PORT=8080  # Optional

# Run the observability node
python -m observability_node.run

# Or run directly
cd observability_node && python app.py
```

For complete documentation, examples, and deployment options, see [observability_node/QUICKSTART.md](observability_node/QUICKSTART.md).

---

## Kubernetes Integration

When deployed in a Kubernetes environment, the System Controller can integrate directly with the cluster API to manage replica scaling.

Key characteristics:

- Scaling operates within configured minimum and maximum bounds
- Deployment name, namespace, and limits are environment-driven
- Secure, authorized API access is required

If Kubernetes is not present, the controller continues monitoring without attempting automated scaling.

---

## Monitoring & Logging

System health data is collected using psutil, providing visibility into:

- CPU load
- Memory consumption
- Disk utilization

The controller supplements these metrics by querying recent database activity and, when available, Redis queue backlogs. Each evaluation cycle logs:

- Observed system state
- Scaling recommendations
- Actions taken (or intentionally skipped)

This design supports transparency, accountability, and continuous improvement of scaling heuristics.

---

## Testing

The project includes a test suite to ensure code quality and reliability.

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_observability_node.py

# Run with coverage report
pytest --cov=peoples_coin --cov-report=html
```

### Test Structure

The test suite covers:
- **Unit tests** — Individual component functionality
- **Integration tests** — Database interactions and API endpoints
- **Observability tests** — Monitoring and metrics collection
- **Import tests** — Module dependencies and configurations

Tests are located in the `/tests` directory and follow standard pytest conventions.

---

## Biological Inspiration

The People's Coin backend is intentionally inspired by biological systems, particularly the human nervous, immune, and endocrine systems.

- Continuous sensing of internal state
- Adaptive responses to environmental stressors
- Maintenance of equilibrium under variable load

In this analogy, the System Controller functions as a central nervous system, interpreting signals and coordinating responses to maintain system health. This biomimetic approach informs both architectural decisions and long-term evolution of the platform.

---

## Technologies & Tools

- **Flask** — Web framework
- **PostgreSQL 15** — Primary datastore
- **SQLAlchemy** — ORM and schema management
- **Docker / Docker Compose** — Containerization
- **Redis (optional)** — Queue management
- **psutil** — System monitoring
- **APScheduler** — Periodic job scheduling
- **Kubernetes Python Client (optional)** — Deployment orchestration

All optional components degrade gracefully when unavailable.

---

## Benefits of Cloning This Repository

Cloning this repository gives you a practical, inspectable backend foundation that you can run and adapt quickly:

- Full access to a modular Flask + SQLAlchemy architecture you can reuse for governance, reputation, or civic platforms.
- A ready-to-evolve data model covering accounts, wallets, goodwill actions, proposals, votes, and audit logs.
- Built-in observability and adaptive system-controller logic to experiment with workload-aware backend behavior.
- Container and infrastructure manifests (Docker, Docker Compose, Kubernetes) to test locally and transition to cloud deployments.
- Migration scripts and tests that make iterative development and schema evolution easier to manage.
- Optional integrations (Redis, Kubernetes) that degrade gracefully, allowing development without a full production stack.

---

## Development & Production Readiness

The backend is designed with operational resilience in mind:

- Works with or without Redis and Kubernetes
- Scaling actions are bounded to prevent resource thrashing
- All automated decisions are logged and auditable
- Modular structure supports incremental extension

This provides a stable foundation for continued development and future production hardening.

---

## Contributing

Contributions are welcome! Here's how you can help:

### How to Contribute

1. **Fork the repository** on GitHub
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** with clear, focused commits
4. **Write or update tests** to cover your changes
5. **Ensure all tests pass**
   ```bash
   pytest
   ```
6. **Submit a pull request** with a clear description of your changes

### Contribution Guidelines

- Follow the existing code style and conventions
- Write clear commit messages
- Update documentation for any new features
- Add tests for new functionality
- Keep pull requests focused on a single feature or fix
- Be respectful and constructive in discussions

### Areas for Contribution

- Bug fixes and issue resolution
- New features and enhancements
- Documentation improvements
- Test coverage expansion
- Performance optimizations
- Security improvements

---

## Troubleshooting

### Common Issues and Solutions

#### Database Connection Errors

**Problem:** `psycopg2.OperationalError: could not connect to server`

**Solution:**
```bash
# Verify PostgreSQL is running
pg_isready

# Check your DATABASE_URL in .env
echo $DATABASE_URL

# Ensure the database exists
createdb peoples_coin
```

#### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'peoples_coin'`

**Solution:**
```bash
# Ensure you're in the virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

#### Port Already in Use

**Problem:** `OSError: [Errno 48] Address already in use`

**Solution:**
```bash
# Find process using the port
lsof -i :8080  # macOS/Linux
netstat -ano | findstr :8080  # Windows

# Kill the process or use a different port
export FLASK_RUN_PORT=8081
```

#### Migration Errors

**Problem:** `alembic.util.exc.CommandError: Can't locate revision identified by...`

**Solution:**
```bash
# Reset migrations (development only)
flask db stamp head
flask db migrate -m "Reset migrations"
flask db upgrade

# Or start fresh
rm -rf migrations/
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

#### Missing Environment Variables

**Problem:** Application crashes with "KeyError" for environment variables

**Solution:**
```bash
# Create .env file with required variables
cp .env.example .env  # if example exists
# Edit .env with your configuration

# Or export manually
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
export SECRET_KEY="your-secret-key"
```

For additional help, please [open an issue](https://github.com/dfeen87/the-peoples-coin-project/issues) on GitHub.

---

## Supporting the Project

This project is **MIT-licensed** because I want people to learn from it, build with it, and carry it forward.

At the same time, this code reflects a lot of personal effort and care. If you find it useful, please consider supporting the work in one or more of these ways:

- ⭐ **Star and share** the repository so more builders can discover it
- 📝 **Keep attribution** in place and reference this project in derivative work
- 🐛 **Open issues**, suggest improvements, or contribute pull requests
- 🤝 **Reach out** if you want to collaborate, sponsor maintenance, or fund roadmap work
- 📢 **Spread the word** — share with communities that might benefit from this platform

Every contribution, whether code, documentation, or feedback, helps make this project better for everyone.

---

## Acknowledgements

I would like to acknowledge **Microsoft Copilot**, and **OpenAI ChatGPT** for their meaningful assistance in refining concepts, improving clarity, and strengthening the overall quality of this work.

## About

The People's Coin backend is a Flask- and PostgreSQL-based system that securely records goodwill actions, manages user and governance data, and dynamically monitors system health. Its System Controller enables adaptive behavior inspired by biological systems, providing a transparent and scalable foundation for community-driven platforms.

**Author:** Don Michael Feeney Jr  
**Repository:** [github.com/dfeen87/the-peoples-coin-project](https://github.com/dfeen87/the-peoples-coin-project)

---

## Closing

The People's Coin backend represents a forward-looking approach to combining public-ledger principles with intelligent system orchestration. By pairing transparent data handling with adaptive resource management, the platform is designed to remain resilient, scalable, and accountable as it grows.

Whether you're building a governance system, a reputation ledger, or exploring adaptive backend architectures, this project provides a solid, well-documented foundation to start from.

**Happy Building! 🚀**
