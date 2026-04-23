#!/usr/bin/env bash
set -e
bash <(curl -sL https://github.com/XTLS/Xray-install/raw/main/install-release.sh) --version latest
systemctl enable xray
echo "xray installed: $(/usr/local/bin/xray version | head -1)"
