"""Тесты генераторов bash-скриптов из ssh/scripts.py.
Проверяем: корректность JSON-конфигов, структуру VLESS-ссылок, Caddy-конфиги.
Никаких реальных SSH-соединений.
"""
import json
import re
import uuid

import pytest

from ssh.scripts import (
    configure_xray_direct,
    minimal_exit_xray,
    make_vless_link,
    setup_caddy_ip,
    setup_caddy_domain,
    deploy_sub_server,
    gen_reality_keys,
    install_xray,
    setup_geo_files,
    generate_client_uuid,
    generate_sub_token,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_json(script: str, marker_start: str, marker_end: str) -> dict:
    """вырезает первый JSON-блок между маркерами heredoc."""
    start = script.index(marker_start) + len(marker_start)
    end = script.index(marker_end, start)
    return json.loads(script[start:end].strip())


def _direct_cfg(n_clients: int = 1, sni: str = "www.microsoft.com") -> dict:
    clients = [{"id": str(uuid.uuid4()), "flow": "xtls-rprx-vision"} for _ in range(n_clients)]
    script = configure_xray_direct("PRIVKEY", "PUBKEY", "SHORTID", sni, clients)
    return _extract_json(script, "'XRAYCFG'\n", "\nXRAYCFG")


def _exit_cfg(sni: str = "www.microsoft.com") -> dict:
    script = minimal_exit_xray("PRIVKEY", "PUBKEY", "SHORTID", sni)
    return _extract_json(script, "'EXITCFG'\n", "\nEXITCFG")


# ── configure_xray_direct ────────────────────────────────────────────────────

class TestConfigureXrayDirect:
    def test_inbound_port_443(self):
        cfg = _direct_cfg()
        assert cfg["inbounds"][0]["port"] == 443

    def test_protocol_vless(self):
        cfg = _direct_cfg()
        assert cfg["inbounds"][0]["protocol"] == "vless"

    def test_security_reality(self):
        cfg = _direct_cfg()
        ss = cfg["inbounds"][0]["streamSettings"]
        assert ss["security"] == "reality"

    def test_reality_has_private_key(self):
        cfg = _direct_cfg()
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["privateKey"] == "PRIVKEY"

    def test_reality_short_ids(self):
        cfg = _direct_cfg()
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert "SHORTID" in rs["shortIds"]

    def test_reality_dest_matches_sni(self):
        cfg = _direct_cfg(sni="custom.sni.example")
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["dest"] == "custom.sni.example:443"
        assert "custom.sni.example" in rs["serverNames"]

    def test_clients_count(self):
        cfg = _direct_cfg(n_clients=3)
        assert len(cfg["inbounds"][0]["settings"]["clients"]) == 3

    def test_freedom_outbound(self):
        cfg = _direct_cfg()
        assert cfg["outbounds"][0]["protocol"] == "freedom"

    def test_sniffing_enabled(self):
        cfg = _direct_cfg()
        sniff = cfg["inbounds"][0]["sniffing"]
        assert sniff["enabled"] is True
        assert "tls" in sniff["destOverride"]

    def test_no_port53_routing(self):
        """правило проекта: нет port:53 в routing rules."""
        cfg = _direct_cfg()
        routing = cfg.get("routing", {})
        rules = routing.get("rules", [])
        for rule in rules:
            ports = str(rule.get("port", ""))
            assert "53" not in ports, f"port 53 найден в routing rule: {rule}"

    def test_network_tcp(self):
        cfg = _direct_cfg()
        assert cfg["inbounds"][0]["streamSettings"]["network"] == "tcp"

    def test_decryption_none(self):
        cfg = _direct_cfg()
        assert cfg["inbounds"][0]["settings"]["decryption"] == "none"


# ── minimal_exit_xray ─────────────────────────────────────────────────────────

class TestMinimalExitXray:
    def test_inbound_port_443(self):
        cfg = _exit_cfg()
        assert cfg["inbounds"][0]["port"] == 443

    def test_single_client(self):
        cfg = _exit_cfg()
        clients = cfg["inbounds"][0]["settings"]["clients"]
        assert len(clients) == 1

    def test_client_flow_xtls(self):
        cfg = _exit_cfg()
        client = cfg["inbounds"][0]["settings"]["clients"][0]
        assert client["flow"] == "xtls-rprx-vision"

    def test_client_id_is_uuid(self):
        cfg = _exit_cfg()
        client_id = cfg["inbounds"][0]["settings"]["clients"][0]["id"]
        uuid.UUID(client_id)  # бросит ValueError если невалидный UUID

    def test_reality_private_key(self):
        cfg = _exit_cfg()
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["privateKey"] == "PRIVKEY"

    def test_freedom_outbound(self):
        cfg = _exit_cfg()
        assert cfg["outbounds"][0]["protocol"] == "freedom"

    def test_no_port53_routing(self):
        cfg = _exit_cfg()
        rules = cfg.get("routing", {}).get("rules", [])
        for rule in rules:
            assert "53" not in str(rule.get("port", ""))

    def test_script_echos_pub_and_sid(self):
        """скрипт должен выводить PUB= и SID= для парсинга в deploy.py."""
        script = minimal_exit_xray("PRV", "PUB_VAL", "SID_VAL", "sni.example")
        assert 'echo "PUB=PUB_VAL"' in script
        assert 'echo "SID=SID_VAL"' in script

    def test_script_echos_client_id(self):
        script = minimal_exit_xray("PRV", "PUB", "SID", "sni.example")
        assert 'echo "CLIENT_ID=' in script


# ── make_vless_link ───────────────────────────────────────────────────────────

class TestMakeVlessLink:
    _CLIENT = "550e8400-e29b-41d4-a716-446655440000"
    _HOST = "1.2.3.4"
    _PUB = "somePublicKey"
    _SID = "abcd1234"
    _SNI = "www.microsoft.com"

    def _link(self, **kw):
        defaults = dict(
            client_uuid=self._CLIENT, host=self._HOST, pub_key=self._PUB,
            short_id=self._SID, sni=self._SNI, name="test",
        )
        defaults.update(kw)
        return make_vless_link(**defaults)

    def test_scheme_vless(self):
        assert self._link().startswith("vless://")

    def test_uuid_in_link(self):
        assert self._CLIENT in self._link()

    def test_host_in_link(self):
        assert self._HOST in self._link()

    def test_default_port_443(self):
        assert "@1.2.3.4:443?" in self._link()

    def test_custom_port(self):
        assert "@1.2.3.4:8443?" in self._link(port=8443)

    def test_security_reality(self):
        assert "security=reality" in self._link()

    def test_pubkey_param(self):
        assert f"pbk={self._PUB}" in self._link()

    def test_shortid_param(self):
        assert f"sid={self._SID}" in self._link()

    def test_sni_param(self):
        assert f"sni={self._SNI}" in self._link()

    def test_flow_xtls(self):
        assert "flow=xtls-rprx-vision" in self._link()

    def test_name_fragment(self):
        assert self._link(name="mynode").endswith("#mynode")

    def test_fingerprint_chrome(self):
        assert "fp=chrome" in self._link()


# ── Caddy configs ─────────────────────────────────────────────────────────────

class TestCaddyConfigs:
    def test_ip_caddy_contains_ip(self):
        script = setup_caddy_ip("5.5.5.5")
        assert "5.5.5.5:9090" in script

    def test_ip_caddy_reverse_proxy(self):
        script = setup_caddy_ip("5.5.5.5")
        assert "reverse_proxy 127.0.0.1:9090" in script

    def test_domain_caddy_contains_domain(self):
        script = setup_caddy_domain("vpn.example.com")
        assert "vpn.example.com:9090" in script

    def test_domain_caddy_reverse_proxy(self):
        script = setup_caddy_domain("vpn.example.com")
        assert "reverse_proxy 127.0.0.1:9090" in script

    def test_caddy_systemctl_restart(self):
        for script in [setup_caddy_ip("1.2.3.4"), setup_caddy_domain("x.com")]:
            assert "systemctl restart caddy" in script


# ── sub server ────────────────────────────────────────────────────────────────

class TestDeploySubServer:
    def test_subs_dir_created(self):
        script = deploy_sub_server("TOKEN")
        assert "mkdir -p /opt/vpn-subs" in script

    def test_systemd_service_created(self):
        script = deploy_sub_server("TOKEN")
        assert "vpn-sub.service" in script

    def test_python_server_port_9090(self):
        script = deploy_sub_server("TOKEN")
        assert "PORT = 9090" in script

    def test_base64_encoding_present(self):
        script = deploy_sub_server("TOKEN")
        assert "base64" in script


# ── geo files script ──────────────────────────────────────────────────────────

class TestGeoFiles:
    def test_downloads_geoip(self):
        script = setup_geo_files()
        assert "ru_geoip.dat" in script

    def test_downloads_geosite(self):
        script = setup_geo_files()
        assert "ru_geosite.dat" in script

    def test_cron_12h(self):
        script = setup_geo_files()
        assert "*/12" in script

    def test_runetfreedom_source(self):
        script = setup_geo_files()
        assert "runetfreedom" in script


# ── install_xray ──────────────────────────────────────────────────────────────

class TestInstallXray:
    def test_uses_xray_install_script(self):
        script = install_xray()
        assert "Xray-install" in script

    def test_enables_systemd(self):
        script = install_xray()
        assert "systemctl enable xray" in script

    def test_set_e(self):
        script = install_xray()
        assert "set -e" in script


# ── gen_reality_keys ──────────────────────────────────────────────────────────

class TestGenRealityKeys:
    def test_uses_x25519(self):
        script = gen_reality_keys()
        assert "x25519" in script

    def test_outputs_pub(self):
        script = gen_reality_keys()
        assert "PUB=" in script

    def test_outputs_prv(self):
        script = gen_reality_keys()
        assert "PRV=" in script

    def test_outputs_sid(self):
        script = gen_reality_keys()
        assert "SID=" in script

    def test_openssl_rand_for_sid(self):
        script = gen_reality_keys()
        assert "openssl rand" in script


# ── helpers ───────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_generate_client_uuid_is_uuid(self):
        uid = generate_client_uuid()
        uuid.UUID(uid)

    def test_generate_sub_token_not_empty(self):
        token = generate_sub_token()
        assert len(token) >= 32

    def test_generate_sub_token_url_safe(self):
        token = generate_sub_token()
        assert re.match(r'^[A-Za-z0-9_-]+$', token)

    def test_tokens_unique(self):
        tokens = {generate_sub_token() for _ in range(100)}
        assert len(tokens) == 100
