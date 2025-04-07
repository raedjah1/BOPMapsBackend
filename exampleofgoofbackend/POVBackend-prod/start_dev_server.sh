#!/bin/bash

# Using remote Redis - no need to start a local Redis server

# Start Celery worker
echo "Starting Celery worker..."
python3 -m celery -A pov_backend worker --loglevel=info > celery_worker.log 2>&1 &
CELERY_WORKER_PID=$!
echo "Started Celery worker with PID $CELERY_WORKER_PID"

# Start Celery beat (scheduler)
echo "Starting Celery beat..."
python3 -m celery -A pov_backend beat --loglevel=info > celery_beat.log 2>&1 &
CELERY_BEAT_PID=$!
echo "Started Celery beat with PID $CELERY_BEAT_PID"

# Wait a moment for Celery to start
sleep 2

# Start Django development server
echo "Starting Django development server..."
python3 manage.py runserver

# Cleanup function to kill all processes when script exits
cleanup() {
    echo "Shutting down services..."
    if [ -n "$CELERY_WORKER_PID" ]; then
        echo "Stopping Celery worker ($CELERY_WORKER_PID)..."
        kill $CELERY_WORKER_PID
    fi
    
    if [ -n "$CELERY_BEAT_PID" ]; then
        echo "Stopping Celery beat ($CELERY_BEAT_PID)..."
        kill $CELERY_BEAT_PID
    fi
    
    echo "All services stopped."
}

# Register the cleanup function to be called on exit
trap cleanup EXIT

# Keep the script running
wait $CELERY_WORKER_PID 