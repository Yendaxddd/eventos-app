#!/bin/bash

# Eventos App Build Script
echo "🚀 Building Eventos App..."

# Bundle the backend code
echo "📦 Bundling backend code..."
/home/Ily/Downloads/migracion\ cosas/Eventos\ stuff\ jajalol/.venv/bin/pyinstaller --onefile --name EventosApp \
--add-data "frontend:frontend" \
--add-data "backend/data:data" \
--hidden-import="fastapi" \
--hidden-import="uvicorn" \
--hidden-import="starlette" \
--hidden-import="pydantic" \
--hidden-import="typing_extensions" \
--hidden-import="anyio" \
--hidden-import="h11" \
--hidden-import="click" \
--hidden-import="websockets" \
--hidden-import="socketio" \
--hidden-import="engineio" \
backend/api/main.py

echo "✅ Build complete! Executable is in the 'dist' directory."
