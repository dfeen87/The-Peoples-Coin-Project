# Global Observability Node — Quick Start Guide

## Overview

The Global Observability Node is a lightweight, read-only REST API that provides safe, non-intrusive access to internal system state for monitoring and observability purposes.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# Required
export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"

# Optional
export OBSERVABILITY_PORT=8080  # Default: 8080
export OBSERVABILITY_HOST=0.0.0.0  # Default: 0.0.0.0
export CELERY_BROKER_URL="redis://localhost:6379/0"  # For Redis metrics
```

### 3. Run the Observability Node

**Option A: Using the standalone runner**
```bash
python -m observability_node.run
```

**Option B: Using the app directly**
```bash
cd observability_node
python app.py
```

## API Endpoints

All endpoints are **read-only** (GET requests only). POST, PUT, PATCH, and DELETE requests are rejected with 405 Method Not Allowed.

### 1. Health Check
```bash
curl http://localhost:8080/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "Global Observability Node",
  "version": "3.1.1",
  "uptime_seconds": 3600.5,
  "timestamp": "2026-02-14T12:00:00.000000+00:00"
}
```

### 2. System State
```bash
curl http://localhost:8080/api/system_state
```

**Response:** Includes CPU%, memory%, disk%, load averages, DB activity, Redis queue depth, K8s status, and last controller evaluation.

### 3. Controller Decisions
```bash
curl http://localhost:8080/api/controller_decisions?limit=10
```

**Response:** Last N controller decisions with recommendations and actions taken.

### 4. Governance State
```bash
curl http://localhost:8080/api/governance_state
```

**Response:** Summary of proposals, votes, and council membership.

### 5. Audit Summary
```bash
curl http://localhost:8080/api/audit_summary?limit=20
```

**Response:** Last N audit log entries with timestamps and context.

## Docker Deployment

Add this to your `docker-compose.yml`:

```yaml
services:
  observability-node:
    build: .
    command: python -m observability_node.run
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/dbname
      - OBSERVABILITY_PORT=8080
    depends_on:
      - db
```

## Kubernetes Deployment

Create a deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: observability-node
spec:
  replicas: 1
  selector:
    matchLabels:
      app: observability-node
  template:
    metadata:
      labels:
        app: observability-node
    spec:
      containers:
      - name: observability-node
        image: your-registry/peoples-coin:latest
        command: ["python", "-m", "observability_node.run"]
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        - name: OBSERVABILITY_PORT
          value: "8080"
---
apiVersion: v1
kind: Service
metadata:
  name: observability-node
spec:
  selector:
    app: observability-node
  ports:
  - port: 8080
    targetPort: 8080
```

## Monitoring & Alerts

You can use tools like Prometheus, Grafana, or Datadog to scrape these endpoints for monitoring:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'peoples-coin-observability'
    metrics_path: '/api/system_state'
    static_configs:
      - targets: ['observability-node:8080']
```

## Security Notes

- **No Authentication Required**: The observability node is read-only and exposes only non-sensitive system state.
- **No Secrets Exposed**: Credentials, keys, and user data are never included in responses.
- **Rate Limiting**: Consider adding rate limiting in production (e.g., nginx, API gateway).
- **Network Security**: Deploy behind a firewall or VPN for sensitive environments.

## Troubleshooting

### "ModuleNotFoundError: No module named 'psutil'"
```bash
pip install psutil
```

### "DATABASE_URL is not set"
Set the environment variable:
```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
```

### Port 8080 already in use
Change the port:
```bash
export OBSERVABILITY_PORT=8081
```

## Support

For issues, questions, or contributions, please refer to the project documentation or open an issue.
