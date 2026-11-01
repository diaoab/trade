#!/usr/bin/env bash
# ============================================================
#  Trade API — Setup initial VPS Ubuntu 22.04 / 24.04
#  Usage  : sudo bash deploy/setup-server.sh --domain api.example.com
#  Lancer UNE SEULE FOIS apres le premier login root sur le VPS
# ============================================================
set -euo pipefail

# ── Parametres configurables ─────────────────────────────────────────────────
APP_USER="tradeapp"
APP_DIR="/var/www/trade-api"
DOMAIN="${DOMAIN:-YOUR_DOMAIN}"   # ou : DOMAIN=api.example.com sudo bash setup-server.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ "$DOMAIN" == "YOUR_DOMAIN" ]]; then
    echo "ATTENTION : DOMAIN non defini."
    echo "  Usage : sudo bash deploy/setup-server.sh --domain api.example.com"
    exit 1
fi

echo "==> [1/8] Mise a jour des paquets"
apt-get update -qq && apt-get upgrade -y -qq

echo "==> [2/8] Installation des dependances systeme"
apt-get install -y -qq \
    curl git ufw cron \
    nginx certbot python3-certbot-nginx \
    ca-certificates \
    docker.io docker-compose-plugin

systemctl enable --now docker cron

echo "==> [3/8] Creation de l'utilisateur applicatif '${APP_USER}'"
id "${APP_USER}" &>/dev/null || useradd -m -s /bin/bash "${APP_USER}"
usermod -aG docker "${APP_USER}"

echo "==> [4/8] Creation de l'arborescence de l'application"
mkdir -p "${APP_DIR}" "${APP_DIR}/backups" /var/www/certbot
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}"

echo "==> [5/8] Configuration du pare-feu (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> [6/8] Certificat SSL via Certbot (webroot)"
# Le site HTTPS reference des certificats encore absents : un site HTTP
# provisoire sert d'abord le challenge ACME.
cat > /etc/nginx/sites-available/trade-api <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
}
NGINX
ln -sf /etc/nginx/sites-available/trade-api /etc/nginx/sites-enabled/trade-api
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

certbot certonly --webroot -w /var/www/certbot \
    -d "${DOMAIN}" \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email

echo "==> [7/8] Configuration Nginx definitive"
cp "${SCRIPT_DIR}/nginx.conf" /etc/nginx/sites-available/trade-api
sed -i "s/YOUR_DOMAIN/${DOMAIN}/g" /etc/nginx/sites-available/trade-api
nginx -t && systemctl reload nginx

echo "==> [8/8] Renouvellement automatique des certificats"
systemctl status certbot.timer --no-pager || true
(crontab -l 2>/dev/null | grep -v "certbot renew"; \
    echo "0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'") | crontab -

echo ""
echo "============================================"
echo " Setup termine pour ${DOMAIN} !"
echo ""
echo " Etapes suivantes (en tant que ${APP_USER}) :"
echo "   1. git clone <repo> ${APP_DIR}"
echo "   2. cd ${APP_DIR}"
echo "   3. cp .env.example .env && nano .env   (remplir TOUTES les valeurs)"
echo "   4. docker compose -f docker-compose.prod.yml up -d --build"
echo "   5. crontab deploy/crontab              (cours du soir, purge, sauvegardes)"
echo "   6. importer les historiques et entrainer le modele (voir README)"
echo "============================================"
