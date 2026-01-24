#!/bin/bash

# Eventos App Quick Start Script
echo "🚀 Starting Eventos App..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed. Please install Python 3.8+"
    exit 1
fi

# Install backend dependencies if needed
echo "📦 Installing backend dependencies..."
cd backend
pip install fastapi uvicorn python-socketio --user --quiet

# Start backend server
echo "🔧 Starting backend server..."
python -m uvicorn api.main:app --host 0.0.0.0 --port 7000 &
BACKEND_PID=$!

# Wait for server to start
sleep 3

# Open frontend in browser
echo "🌐 Opening frontend..."
if command -v xdg-open &> /dev/null; then
    xdg-open ../frontend/index.html
elif command -v open &> /dev/null; then
    open ../frontend/index.html
else
    echo "Please open frontend/index.html in your browser"
fi

echo "✅ Eventos App is running!"
echo "Backend: http://localhost:7000"
echo "Frontend: Open frontend/index.html in your browser"
echo ""
echo "Press Ctrl+C to stop the server"

# Wait for Ctrl+C
trap "kill $BACKEND_PID 2>/dev/null; echo '🛑 Server stopped'; exit" INT
wait $BACKEND_PID
