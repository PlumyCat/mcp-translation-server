# MCP Translation Server

A minimal Python API server for document translation, ready for deployment.

## Features
- Simple deployment with PowerShell script (`deploy_simple.ps1`)
- Virtual environment setup for Python

## Quick Start

### 1. Clone the repository
```sh
git clone <your-repo-url>
cd mcp-translation-server
```

### 2. Create and activate a virtual environment
On Windows:
```sh
python -m venv .venv
.venv\Scripts\activate
```
On Linux/macOS:
```sh
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```sh
pip install -r requirements.txt
```

### 4. Deploy
```sh
./deploy_simple.ps1
```

## Essential Files
- `api_server.py` / `server.py` : Main API server
- `requirements.txt` : Python dependencies
- `deploy_simple.ps1` : Deployment script
- `src/` : Source code (config, services, models)

## Notes
- All non-essential files are archived in `archive/` and ignored by git.
- Always use a virtual environment for Python development.
