#!/bin/bash
# Stock Predictor Startup Script
# Starts both the backend and the Tauri app

# Start the backend server in background
cd /Users/jonathanchang/Desktop/Self\ hosted\ apps/Stock/Stock\ Predictor/backend
python3 start_server.py &

# Wait for the server to start
sleep 3

# Change to the frontend directory and start Tauri
cd /Users/jonathanchang/Desktop/Self\ hosted\ apps/Stock/Stock\ Predictor
nohup npm run tauri:dev > /tmp/tauri.log 2>&1 &

echo "Stock Predictor started!"
echo "Backend: http://127.0.0.1:8000"
echo "UI: http://localhost:1420"
echo "Visit http://localhost:1420 to use the application"