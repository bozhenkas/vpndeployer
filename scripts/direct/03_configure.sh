#!/usr/bin/env bash
# вызывается с подставленным конфигом из ssh/scripts.py::configure_xray_direct
set -e
systemctl restart xray
sleep 2
systemctl is-active xray
