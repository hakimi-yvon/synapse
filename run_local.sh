#!/usr/bin/env bash
# ==============================================================================
# Synapse - Script de lancement tout-en-un pour l'environnement local
# Lance le worker Celery en arrière-plan et le bot Telegram au premier plan.
# Un simple Ctrl+C arrête l'ensemble proprement.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Arrêt propre de tous les processus fils lors de la fermeture (Ctrl+C)
trap 'echo -e "\n🛑 Arrêt de Synapse..."; kill $(jobs -p) 2>/dev/null; exit 0' SIGINT SIGTERM EXIT

echo "=================================================="
echo "⚡ DÉMARRAGE DE SYNAPSE EN LOCAL"
echo "=================================================="

# 1. Démarrage du Celery Worker en arrière-plan
echo "👷 Lancement du Celery Worker..."
./venv/bin/celery -A synapse worker --loglevel=INFO &
sleep 2

# 2. Démarrage du Bot Telegram au premier plan
echo "🤖 Lancement du Bot Telegram en écoute..."
./venv/bin/python manage.py run_telegram_bot
