FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and verify Python
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 --version

# Copy requirements
COPY discord-bot/requirements*.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY discord-bot/ ./

# Create data directories
RUN mkdir -p data/achievements data/skill_trees data/special_objects logs

# Verify Python and modules
RUN python3 -c "import discord; import requests; print('✓ Dependencies OK')"

# Run the bot
CMD ["python3", "advanced_qte_hp_system_debug.py"]
