# Quick Start Guide - Full Stack

## Running Backend + Frontend Together

### Option 1: Separate Terminals (Recommended)

**Terminal 1 - Backend**
```bash
cd project-foundation
python -m venv .venv
.venv\Scripts\activate      # Windows
# or
source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend will run on: http://localhost:8000

**Terminal 2 - Frontend**
```bash
cd project-foundation/frontend
npm install
npm run dev
```

Frontend will run on: http://localhost:3000

### Option 2: Single Terminal (Background)

**Windows (PowerShell)**
```powershell
# Start backend
cd project-foundation
Start-Process powershell -ArgumentList "-Command", "uvicorn app.main:app --reload"

# Start frontend
cd frontend
npm run dev
```

**Mac/Linux (Bash)**
```bash
# Start backend
cd project-foundation
uvicorn app.main:app --reload &

# Start frontend
cd frontend
npm run dev
```

## Verification

1. **Backend Health Check**
   ```bash
   curl http://localhost:8000/health
   ```
   Expected: `{"status":"healthy"}`

2. **Frontend Access**
   Open browser: http://localhost:3000
   
3. **API Connection**
   Check browser console for API calls

## Environment Setup

### Backend (.env)
```env
# Database
MONGODB_URL=mongodb://localhost:27017
DB_NAME=ai_testing_platform

# LLM
OPENAI_API_KEY=your_key_here

# Storage
STORAGE_BASE_PATH=./storage

# Playwright
PLAYWRIGHT_BROWSER=chromium
PLAYWRIGHT_HEADLESS=true
```

### Frontend (.env.local)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Common Issues

### Backend Issues

**ImportError: No module named 'app'**
```bash
# Ensure you're in the project-foundation directory
cd project-foundation
python -m app.main
```

**Port 8000 already in use**
```bash
# Use different port
uvicorn app.main:app --reload --port 8001

# Update frontend .env.local
NEXT_PUBLIC_API_URL=http://localhost:8001
```

### Frontend Issues

**Cannot connect to backend**
1. Verify backend is running
2. Check NEXT_PUBLIC_API_URL in .env.local
3. Look for CORS errors in browser console

**Port 3000 already in use**
```bash
# Next.js will auto-suggest 3001
# or specify manually
npm run dev -- -p 3001
```

## Quick Commands Reference

### Backend
```bash
# Start dev server
uvicorn app.main:app --reload

# Run tests
pytest

# Type check
mypy app/

# Format code
black app/
```

### Frontend
```bash
# Start dev server
npm run dev

# Build production
npm run build

# Type check
npm run type-check

# Lint
npm run lint
```

## Architecture Overview

```
┌─────────────────────────────────────────┐
│         Browser (localhost:3000)        │
│  Next.js 15 Frontend + React + Tailwind│
└─────────────┬───────────────────────────┘
              │ HTTP/REST API
              │
┌─────────────▼───────────────────────────┐
│      FastAPI Backend (localhost:8000)   │
│  Python + Pydantic + LangGraph + OpenAI │
└─────────────┬───────────────────────────┘
              │
    ┌─────────┴──────────┐
    │                    │
┌───▼────┐        ┌──────▼─────┐
│MongoDB │        │  Playwright│
│(Future)│        │  + Browser │
└────────┘        └────────────┘
```

## Development Workflow

1. **Start Backend First**
   - Backend provides API endpoints
   - Runs database migrations
   - Initializes services

2. **Start Frontend**
   - Connects to backend API
   - Displays UI
   - Makes API calls

3. **Make Changes**
   - Backend: Auto-reloads on file change
   - Frontend: Hot-reloads on file change

4. **Test Changes**
   - Backend: http://localhost:8000/docs (Swagger)
   - Frontend: http://localhost:3000

## Production Deployment

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Frontend
```bash
# Install dependencies
npm ci

# Build
npm run build

# Start
npm start
```

## Monitoring

### Backend Logs
```bash
tail -f app.log
```

### Frontend Logs
Check browser DevTools:
- Console tab: JavaScript errors
- Network tab: API calls
- React DevTools: Component tree

### API Documentation
http://localhost:8000/docs (Swagger UI)
http://localhost:8000/redoc (ReDoc)

## Stopping Services

### Graceful Shutdown
```bash
# Backend: Ctrl+C in terminal
# Frontend: Ctrl+C in terminal
```

### Force Kill (if needed)

**Windows**
```powershell
# Find process
Get-Process | Where-Object {$_.Port -eq 8000}

# Kill
Stop-Process -Id <PID>
```

**Mac/Linux**
```bash
# Find and kill backend
lsof -ti:8000 | xargs kill -9

# Find and kill frontend
lsof -ti:3000 | xargs kill -9
```

## Next Steps

1. Create your first project via UI
2. Run a test workflow
3. Review generated artifacts
4. Approve test plans

Happy Testing! 🚀
