#!/usr/bin/env bash
# минимальная установка xray на exit-ноду; конфиг подставляется из scripts.py
set -e
bash <(curl -sL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) --version latest
systemctl enable xray
echo "xray ready"
