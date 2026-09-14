#!/bin/bash
# Respaldo diario de VetCare vía cron. Llama al comando CLI de la app, que ya
# comprime (gzip) y rota (30 días) — ver commands.py.
#
# Instalar en crontab de www-data, por ejemplo a las 3:00 a.m. hora Bogotá:
#   0 3 * * * /var/www/vetcare/deploy/backup.sh >> /var/www/vetcare/logs/backup.log 2>&1

set -euo pipefail

DIR_APP="/var/www/vetcare"
DIR_BACKUPS="$DIR_APP/backups"

cd "$DIR_APP"
source venv/bin/activate
export FLASK_APP=app.py

flask backup dump --directorio "$DIR_BACKUPS" --dias-rotacion 30
