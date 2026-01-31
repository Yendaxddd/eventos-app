FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Verify Python installation
RUN python3 --version && pip3 --version

# Copy requirements FIRST (from discord-bot directory)
COPY discord-bot/requirements.txt ./

# Install Python dependencies with explicit error handling
RUN if [ ! -f requirements.txt ]; then echo "ERROR: requirements.txt not found!"; exit 1; fi && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy bot code (entire discord-bot directory)
COPY discord-bot/ ./

# Create data directories
RUN mkdir -p data/achievements data/skill_trees data/special_objects logs

# Verify Python and critical modules
RUN python3 -c "import sys; print(f'Python: {sys.version}'); import discord; import aiohttp; print('✓ All dependencies OK')"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import discord" || exit 1

# Run the bot
CMD ["python3", "advanced_qte_hp_system_debug.py"]
