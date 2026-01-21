# Use Python 3.12 slim as base
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright and Xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    tzdata \
    fonts-liberation \
    git \
    unzip \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python -m pip install --upgrade pip

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers AND their system dependencies
RUN python -m playwright install chromium --with-deps

# Copy project files
COPY . .

# Expose Django port
EXPOSE 8000

# We use xvfb-run to provide a virtual display for Playwright even in headless mode
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]