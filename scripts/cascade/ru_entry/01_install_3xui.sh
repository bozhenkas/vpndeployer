#!/usr/bin/env bash
set -e
# устанавливаем 3X-UI без интерактивного ввода
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh) <<< $'\n\n\n\n'
systemctl enable x-ui
systemctl start x-ui
sleep 3
systemctl is-active x-ui
