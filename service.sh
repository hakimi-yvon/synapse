#!/usr/bin/env bash
# ==============================================================================
# Synapse - Script de gestion du service systemd en tâche de fond
# Permet d'installer, démarrer, arrêter, redémarrer et suivre les logs du bot.
# ==============================================================================

SERVICE_NAME="synapse-bot.service"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$1" in
    install|setup)
        echo "📦 Configuration du service systemd..."
        mkdir -p "$USER_SYSTEMD_DIR"
        cp "$REPO_DIR/$SERVICE_NAME" "$USER_SYSTEMD_DIR/$SERVICE_NAME"
        loginctl enable-linger "$USER" 2>/dev/null || true
        systemctl --user daemon-reload
        systemctl --user enable "$SERVICE_NAME"
        echo "✅ Service installé et activé pour démarrer automatiquement avec le système !"
        echo "👉 Lancez './service.sh start' pour démarrer le bot."
        ;;
    start)
        echo "🚀 Démarrage du service Synapse..."
        systemctl --user start "$SERVICE_NAME"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    stop)
        echo "🛑 Arrêt du service Synapse..."
        systemctl --user stop "$SERVICE_NAME"
        ;;
    restart)
        echo "🔄 Redémarrage du service Synapse..."
        systemctl --user restart "$SERVICE_NAME"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    status)
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    logs)
        journalctl --user -u "$SERVICE_NAME" -f
        ;;
    uninstall)
        echo "🗑️ Désinstallation du service..."
        systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
        rm -f "$USER_SYSTEMD_DIR/$SERVICE_NAME"
        systemctl --user daemon-reload
        echo "✅ Service désinstallé."
        ;;
    *)
        echo "Usage: $0 {install|start|stop|restart|status|logs|uninstall}"
        exit 1
        ;;
esac
