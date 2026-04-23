#!/usr/bin/env bash
set -e
apt-get install -y git make gcc libnetfilter-queue-dev
git clone --depth 1 https://github.com/bol-van/zapret /opt/zapret 2>/dev/null || \
    git -C /opt/zapret pull
cd /opt/zapret
./install_bin.sh
./install_prereq.sh
# неинтерактивная установка с nfqws
NFQWS=1 ./install_easy.sh
