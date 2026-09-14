# Despliegue de VetCare (Sandía) en un VPS Ubuntu

Pasos para un VPS Ubuntu 22.04/24.04 limpio, con Nginx + Gunicorn + PostgreSQL.

## 1 · Paquetes del sistema

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv postgresql postgresql-client \
    nginx certbot python3-certbot-nginx git
```

## 2 · Base de datos

```bash
sudo -u postgres psql -c "CREATE ROLE vetcare WITH LOGIN PASSWORD 'CAMBIA_ESTA_CLAVE';"
sudo -u postgres psql -c "CREATE DATABASE vetcare OWNER vetcare ENCODING 'UTF8';"
```

## 3 · Clonar y preparar la aplicación

```bash
sudo mkdir -p /var/www/vetcare
sudo chown $USER:www-data /var/www/vetcare
git clone <url-del-repositorio> /var/www/vetcare
cd /var/www/vetcare

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edita .env: SECRET_KEY (python -c "import secrets; print(secrets.token_hex(32))"),
# DATABASE_URL=postgresql+psycopg://vetcare:CAMBIA_ESTA_CLAVE@localhost:5432/vetcare,
# BEHIND_PROXY=true, SESSION_COOKIE_SECURE=true
nano .env
```

## 4 · Migraciones y primer administrador

```bash
flask db upgrade
flask crear-admin
```

## 5 · Permisos (Gunicorn corre como www-data, nunca como root)

```bash
sudo chown -R www-data:www-data /var/www/vetcare
sudo chmod -R750 /var/www/vetcare
```

## 6 · Servicio systemd

```bash
sudo cp deploy/vetcare.service /etc/systemd/system/vetcare.service
sudo systemctl daemon-reload
sudo systemctl enable --now vetcare
sudo systemctl status vetcare
```

## 7 · Nginx + HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/vetcare
# Reemplaza ⟨dominio⟩ dentro del archivo por el dominio real
sudo ln -s /etc/nginx/sites-available/vetcare /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <dominio>
```

## 8 · Respaldo automático

```bash
chmod +x deploy/backup.sh
sudo crontab -u www-data -e
# Agrega: 0 3 * * * /var/www/vetcare/deploy/backup.sh >> /var/www/vetcare/logs/backup.log 2>&1
```

Restaurar un respaldo manualmente:

```bash
flask backup restore backups/vetcare_backup_AAAAMMDD_HHMMSS.sql.gz
```

## 9 · Actualizar la aplicación (despliegues siguientes)

```bash
cd /var/www/vetcare
git pull
source venv/bin/activate
pip install -r requirements.txt
flask db upgrade
sudo systemctl restart vetcare
```

## Checklist de verificación posterior

- `sudo systemctl status vetcare` → `active (running)`, sin reinicios en bucle.
- `curl -I https://<dominio>/salud` → `200` con `{"estado":"ok"}`.
- Login funciona y `SESSION_COOKIE_SECURE=true` no bloquea la sesión (requiere HTTPS ya activo).
- `flask backup dump` corre sin errores manualmente antes de confiar en el cron.
- Los logs de la app están en `logs/vetcare.log` (definido por `LOG_FILE` en `.env`).
