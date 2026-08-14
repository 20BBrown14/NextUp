# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

# Want to help us make this template better? Share your feedback here: https://forms.gle/ybq9Krt8jtBL3iCk7

# This Dockerfile uses Docker Hardened Images (DHI) for enhanced security.
# For more information, see https://docs.docker.com/dhi/
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

# Define timezone ARG with default UTC, then assign it to the TZ ENV variable
ARG TZ=UTC
ENV TZ=${TZ}

# Prevents Python from writing pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Download dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# Copy source code and scripts into the container
COPY . .

# Ensure the rotation script is executable
RUN chmod +x /app/scripts/rotate_logs.sh

ENV ENV=prod
ENV APP_HOST=0.0.0.0
ENV APP_PORT=5777
EXPOSE $APP_PORT

# Execute log rotation script first to get the log file path, then launch FastAPI
CMD ["sh", "-c", "LOG_FILE=$(sh /app/scripts/rotate_logs.sh); RELOAD=\"\"; [ \"$ENV\" = \"dev\" ] && RELOAD=\"--reload\"; fastapi run server.py --host ${APP_HOST} --port ${APP_PORT} $RELOAD 2>&1 | tee -a \"$LOG_FILE\""]
