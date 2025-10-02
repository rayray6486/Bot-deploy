#!/bin/bash
set -e

echo "🔄 Updating system..."
sudo apt update && sudo apt upgrade -y

echo "⚙️ Installing dependencies..."
sudo apt install -y python3 python3-pip git

echo "📥 Cloning repo..."
if [ ! -d "bot-deploy" ]; then
  git clone https://github.com/rayray6486/bot-deploy.git
fi
cd bot-deploy

echo "📦 Installing Python packages..."
pip3 install -r requirements.txt

echo "🚀 Starting bot..."
python3 bot.py
