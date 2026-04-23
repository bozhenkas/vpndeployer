"""bash-скрипты для деплоя, передаются на сервер через SSH."""
import json
import secrets
import uuid

# подтягивается из config при вызове функций, не при импорте модуля
_GOIDA_VPN_REPO = "https://github.com/bozhenkas/goida-vpn"
_GOIDA_VPN_TAG = "v1.0.0"  # переопределяется через config в deploy.py


def install_xray() -> str:
    return r"""
set -e
bash <(curl -sL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) --version latest
systemctl enable xray
"""


def gen_reality_keys() -> str:
    return r"""
set -e
KEYS=$(/usr/local/bin/xray x25519)
PUB=$(echo "$KEYS" | grep "Public key" | awk '{print $3}')
PRV=$(echo "$KEYS" | grep "Private key" | awk '{print $3}')
SID=$(openssl rand -hex 8)
echo "PUB=$PUB"
echo "PRV=$PRV"
echo "SID=$SID"
"""


def configure_xray_direct(
    prv_key: str, pub_key: str, short_id: str, sni: str, clients: list[dict]
) -> str:
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "port": 443,
                "protocol": "vless",
                "settings": {
                    "clients": clients,
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{sni}:443",
                        "xver": 0,
                        "serverNames": [sni],
                        "privateKey": prv_key,
                        "shortIds": [short_id],
                    },
                },
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            }
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
    }
    cfg_json = json.dumps(config, ensure_ascii=False, indent=2).replace("'", "'\\''")
    return f"""
set -e
cat > /usr/local/etc/xray/config.json << 'XRAYCFG'
{json.dumps(config, ensure_ascii=False, indent=2)}
XRAYCFG
systemctl restart xray
sleep 2
systemctl is-active xray
"""


def setup_caddy_ip(ip: str) -> str:
    # Let's Encrypt поддерживает IP-сертификаты с 2024; Caddy получает их автоматически
    return f"""
set -e
apt-get install -y caddy 2>/dev/null || snap install caddy --classic
cat > /etc/caddy/Caddyfile << 'CADDYCFG'
{ip}:9090 {{
    reverse_proxy 127.0.0.1:9090
}}
CADDYCFG
systemctl enable caddy
systemctl restart caddy
"""


def setup_caddy_domain(domain: str) -> str:
    return f"""
set -e
apt-get install -y caddy 2>/dev/null || snap install caddy --classic
cat > /etc/caddy/Caddyfile << 'CADDYCFG'
{domain}:9090 {{
    reverse_proxy 127.0.0.1:9090
}}
CADDYCFG
systemctl enable caddy
systemctl restart caddy
"""


def deploy_sub_server(token: str) -> str:
    """минимальный HTTP-сервер подписки на python3 (stdlib), запускается как systemd unit"""
    sub_script = r"""#!/usr/bin/env python3
import http.server, base64, os, sys

SUBS_DIR = "/opt/vpn-subs"
PORT = 9090

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        token = self.path.strip("/").split("/")[-1]
        path = os.path.join(SUBS_DIR, token)
        if not os.path.isfile(path):
            self.send_response(404); self.end_headers(); return
        data = open(path, "rb").read()
        enc = base64.b64encode(data)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Profile-Update-Interval", "12")
        self.end_headers()
        self.wfile.write(enc)

http.server.HTTPServer(("127.0.0.1", PORT), H).serve_forever()
"""
    return f"""
set -e
mkdir -p /opt/vpn-subs
cat > /opt/sub-server.py << 'SUBPY'
{sub_script}
SUBPY
chmod +x /opt/sub-server.py
cat > /etc/systemd/system/vpn-sub.service << 'SVC'
[Unit]
Description=VPN subscription server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/sub-server.py
Restart=always

[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable vpn-sub
systemctl restart vpn-sub
"""


def install_goida_vpn(repo: str, tag: str, bot_token: str, owner_id: int) -> str:
    """клонирует goida-vpn с GitHub по тегу и запускает как systemd service."""
    return f"""
set -e
apt-get install -y git python3

# клонируем конкретный тег
INSTALL_DIR=/opt/goida-vpn
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" fetch --tags
    git -C "$INSTALL_DIR" checkout {tag}
else
    git clone --depth 1 --branch {tag} {repo} "$INSTALL_DIR"
fi

# создаём структуру данных (бот работает в /root/vpn-bot/)
mkdir -p /root/vpn-bot /root/vpn-bot/subscriptions
ln -sf "$INSTALL_DIR/bot/vpn-bot.py" /root/vpn-bot/vpn-bot.py 2>/dev/null || true

# .env для бота
if [ ! -f /root/vpn-bot/.env ]; then
    cat > /root/vpn-bot/.env << 'ENVFILE'
BOT_TOKEN={bot_token}
ENVFILE
fi

# systemd unit
cat > /etc/systemd/system/vpn-bot.service << 'SVC'
[Unit]
Description=goida-vpn management bot
After=network.target x-ui.service

[Service]
WorkingDirectory=/root/vpn-bot
EnvironmentFile=/root/vpn-bot/.env
ExecStart=/usr/bin/python3 /root/vpn-bot/vpn-bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl enable vpn-bot
systemctl restart vpn-bot
sleep 2
systemctl is-active vpn-bot
echo "goida-vpn {tag} installed from {repo}"
"""


def install_3xui() -> str:
    return r"""
set -e
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh) << 'EOF'


EOF
"""


def install_zapret() -> str:
    return r"""
set -e
apt-get install -y git make gcc
git clone --depth 1 https://github.com/bol-van/zapret /opt/zapret || \
    (cd /opt/zapret && git pull)
cd /opt/zapret
./install_bin.sh
./install_prereq.sh
./install_easy.sh
"""


def install_adguard() -> str:
    return r"""
set -e
curl -sS -o /tmp/adguard_install.sh \
    https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh
sh /tmp/adguard_install.sh
/opt/AdGuardHome/AdGuardHome -s install
"""


def setup_geo_files() -> str:
    return r"""
set -e
GEO_DIR=/usr/local/x-ui/bin
mkdir -p "$GEO_DIR"
curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/ru_geoip.dat \
    -o "$GEO_DIR/ru_geoip.dat"
curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/ru_geosite.dat \
    -o "$GEO_DIR/ru_geosite.dat"
# cron 12h
(crontab -l 2>/dev/null | grep -v geo_update; \
 echo "0 */12 * * * curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/ru_geoip.dat -o $GEO_DIR/ru_geoip.dat && curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/ru_geosite.dat -o $GEO_DIR/ru_geosite.dat && x-ui restart # geo_update") | crontab -
"""


def minimal_exit_xray(prv_key: str, pub_key: str, short_id: str, sni: str) -> str:
    client_id = str(uuid.uuid4())
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "port": 443,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": client_id, "flow": "xtls-rprx-vision"}],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": f"{sni}:443",
                        "xver": 0,
                        "serverNames": [sni],
                        "privateKey": prv_key,
                        "shortIds": [short_id],
                    },
                },
            }
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
    }
    return f"""
set -e
bash <(curl -sL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) --version latest
cat > /usr/local/etc/xray/config.json << 'EXITCFG'
{json.dumps(config, ensure_ascii=False, indent=2)}
EXITCFG
systemctl enable xray
systemctl restart xray
sleep 2
systemctl is-active xray
echo "CLIENT_ID={client_id}"
echo "PUB={pub_key}"
echo "SID={short_id}"
"""


def make_vless_link(
    client_uuid: str,
    host: str,
    pub_key: str,
    short_id: str,
    sni: str,
    name: str,
    port: int = 443,
) -> str:
    return (
        f"vless://{client_uuid}@{host}:{port}"
        f"?security=reality&pbk={pub_key}&sid={short_id}"
        f"&sni={sni}&fp=chrome&type=tcp&flow=xtls-rprx-vision"
        f"#{name}"
    )


def generate_sub_token() -> str:
    return secrets.token_urlsafe(32)


def generate_client_uuid() -> str:
    return str(uuid.uuid4())
