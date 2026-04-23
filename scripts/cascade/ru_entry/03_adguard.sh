#!/usr/bin/env bash
set -e
curl -sS -o /tmp/adguard_install.sh \
    https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh
sh /tmp/adguard_install.sh
/opt/AdGuardHome/AdGuardHome -s install
/opt/AdGuardHome/AdGuardHome -s start
