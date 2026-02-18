FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and schedule files
COPY bot_utils.py .
COPY main.py .
COPY notify_workouts.py .
COPY schedule_9907.json .
COPY schedule_10002.json .
