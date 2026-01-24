#!/bin/bash
# Discord Bot Runner Script
# This script runs the Discord bot with sudo for keyboard access

cd "$(dirname "$0")"

echo "🤖 Starting Discord Bot with Keyboard Support..."
echo "📍 Working directory: $(pwd)"
echo ""
echo "⚠️  Installing dependencies for root Python environment..."

# Install dependencies for root Python
/usr/bin/python3 -m pip install -q --break-system-packages discord.py requests python-dotenv rich keyboard 2>/dev/null || \
/usr/bin/python3 -m pip install -q discord.py requests python-dotenv rich keyboard

echo ""
echo "✓ Dependencies installed"
echo "🚀 Starting bot with sudo..."
echo ""

# Run with sudo to access keyboard
exec /usr/bin/python3 advanced_qte_hp_system_debug.py
