#!/usr/bin/env bash
# скачиваем geo-файлы от runetfreedom и настраиваем cron
set -e
GEO_DIR=/usr/local/x-ui/bin
mkdir -p "$GEO_DIR"

dl() {
    curl -sL "https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/$1" \
         -o "$GEO_DIR/$1"
}
dl ru_geoip.dat
dl ru_geosite.dat

# cron 12h автообновление
CRON_CMD="0 */12 * * * curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/ru_geoip.dat -o $GEO_DIR/ru_geoip.dat && curl -sL https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/ru_geosite.dat -o $GEO_DIR/ru_geosite.dat && x-ui restart # geo_update"
(crontab -l 2>/dev/null | grep -v geo_update; echo "$CRON_CMD") | crontab -
echo "geo files ok"
