# Discord Bot Installation Guide

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- C++ compiler (required for building some Python packages)

## System Dependencies

Before installing Python packages, you need to install system-level dependencies:

### On Bazzite/Fedora Atomic (rpm-ostree systems):
```bash
# Install development tools via rpm-ostree
rpm-ostree install gcc-c++ python3-devel

# After installation, reboot to apply changes
sudo reboot
```

**Alternative for Bazzite - Use Distrobox/Toolbox:**
```bash
# Create a development container (recommended for Bazzite)
distrobox create --name devbox --image fedora:latest
distrobox enter devbox

# Inside the container, install development tools
sudo dnf install gcc-c++ python3-devel python3-pip
```

### On Fedora/RHEL/CentOS (traditional):
```bash
sudo dnf install gcc-c++ python3-devel
```

### On Ubuntu/Debian:
```bash
sudo apt-get install g++ python3-dev
```

### On Arch Linux:
```bash
sudo pacman -S gcc python
```

**Note:** The error you encountered is because numpy (required by spaCy) needs a C++ compiler to build. On immutable distributions like Bazzite, using Distrobox is the recommended approach for development environments.

## Installation Steps

### 1. Install Discord.py

The bot requires the `discord.py` library. Install it with:

```bash
cd legacy-discord-bot
pip install discord.py
```

### 2. Install Basic Dependencies First

Install all core dependencies (no build issues on Python 3.14):

```bash
pip install requests python-dotenv flask keyboard h11 rich
```

### 3. Install NLP Dependencies (Optional - Skip if build issues)

The bot uses NLP for action detection, but this is **optional** if you encounter build errors with Python 3.14:

**Option A: Try installing spaCy (may fail on Python 3.14+):**
```bash
pip install -r requirements_nlp.txt
python -m spacy download en_core_web_sm
python -m spacy download es_core_news_sm
```

**Option B: Skip NLP (bot will work without it):**
If you encounter build errors, you can skip the NLP dependencies. The bot has fallback logic that works without spaCy:
```bash
# Just install the core requirements
pip install discord.py requests python-dotenv flask
```

**Note:** The bot's NLP features are for advanced action detection. The basic functionality (HP system, damage calculation, API integration) works fine without spaCy.

### 4. Install Additional Dependencies

If you encounter any missing modules, install them individually:

```bash
pip install python-dotenv
pip install requests  # For API communication
```

### 5. Configure Environment Variables

Create or update the `.env` file in the `legacy-discord-bot` directory:

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
```

Replace `your_discord_bot_token_here` with your actual Discord bot token.

## Quick Install Script

You can also create this installation script:

```bash
#!/bin/bash
cd legacy-discord-bot

echo "Installing Discord.py..."
pip install discord.py

echo "Installing NLP dependencies..."
pip install -r requirements_nlp.txt

echo "Downloading spaCy language models..."
python -m spacy download en_core_web_sm
python -m spacy download es_core_news_sm

echo "Installing additional dependencies..."
pip install python-dotenv requests

echo "Installation complete!"
```

Save as `install_bot_deps.sh` and run:
```bash
chmod +x install_bot_deps.sh
./install_bot_deps.sh
```

## Running the Bot

Once all dependencies are installed:

### 1. Start the Eventos API
```bash
cd eventos-app
./start.sh
```

### 2. Start the Discord Bot
```bash
cd legacy-discord-bot
python advanced_qte_hp_system_debug.py
```

## Troubleshooting

### ModuleNotFoundError: No module named 'discord'
- Solution: `pip install discord.py`

### Missing spaCy models
- Solution: `python -m spacy download en_core_web_sm`

### API Connection Failed
- Make sure the Eventos API is running on `http://localhost:7001`
- Check that `./start.sh` completed successfully in the eventos-app directory

### Permission Errors
- You may need to use `pip3` instead of `pip`
- On some systems: `python3 -m pip install discord.py`

## Verify Installation

Test that all modules are available:

```python
python -c "import discord; print('discord.py:', discord.__version__)"
python -c "import spacy; print('spacy:', spacy.__version__)"
python -c "import flask; print('flask:', flask.__version__)"
```

All commands should print version numbers without errors.
