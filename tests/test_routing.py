"""Тесты xray routing rules для direct и cascade.
Правила проекта (из CLAUDE.md):
- нет port:53 в routing rules
- googleapis/gstatic/googleusercontent — никогда в YouTube-листах
- heartbeatPeriod:30 на WS inbounds (если есть)
- outbound для заблокированного трафика → exit-сервер (cascade)
- российский трафик → direct (cascade)
"""
import json
import uuid

import pytest

from ssh.scripts import (
    configure_xray_direct,
    minimal_exit_xray,
    make_vless_link,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg_direct(n=1, sni="www.microsoft.com") -> dict:
    clients = [{"id": str(uuid.uuid4()), "flow": "xtls-rprx-vision"} for _ in range(n)]
    script = configure_xray_direct("PRV", "PUB", "SID", sni, clients)
    start = script.index("'XRAYCFG'\n") + len("'XRAYCFG'\n")
    end = script.index("\nXRAYCFG", start)
    return json.loads(script[start:end].strip())


def _cfg_exit(sni="www.microsoft.com") -> dict:
    script = minimal_exit_xray("PRV", "PUB", "SID", sni)
    start = script.index("'EXITCFG'\n") + len("'EXITCFG'\n")
    end = script.index("\nEXITCFG", start)
    return json.loads(script[start:end].strip())


def _all_routing_rules(*cfgs: dict) -> list[dict]:
    rules = []
    for cfg in cfgs:
        rules.extend(cfg.get("routing", {}).get("rules", []))
    return rules


# ── port-53 prohibition ───────────────────────────────────────────────────────

class TestNoPort53:
    """Ни один конфиг не должен содержать port:53 в routing rules."""

    def test_direct_no_port53(self):
        rules = _all_routing_rules(_cfg_direct())
        for rule in rules:
            port = str(rule.get("port", ""))
            assert "53" not in port.split(",") and port != "53", \
                f"найден port 53 в direct routing: {rule}"

    def test_exit_no_port53(self):
        rules = _all_routing_rules(_cfg_exit())
        for rule in rules:
            port = str(rule.get("port", ""))
            assert "53" not in port.split(",") and port != "53", \
                f"найден port 53 в exit routing: {rule}"

    def test_direct_multiple_clients_no_port53(self):
        rules = _all_routing_rules(_cfg_direct(n=5))
        port_values = [str(r.get("port", "")) for r in rules]
        assert not any("53" in p for p in port_values)


# ── outbound structure ────────────────────────────────────────────────────────

class TestOutboundStructure:
    def test_direct_config_has_exactly_one_outbound(self):
        cfg = _cfg_direct()
        assert len(cfg["outbounds"]) == 1

    def test_direct_outbound_is_freedom(self):
        cfg = _cfg_direct()
        assert cfg["outbounds"][0]["protocol"] == "freedom"

    def test_exit_outbound_is_freedom(self):
        """exit-нода сама является выходным узлом, protocol=freedom."""
        cfg = _cfg_exit()
        assert cfg["outbounds"][0]["protocol"] == "freedom"

    def test_direct_no_block_outbound(self):
        """direct-конфиг не должен блокировать трафик."""
        cfg = _cfg_direct()
        protocols = [o["protocol"] for o in cfg["outbounds"]]
        assert "blackhole" not in protocols

    def test_freedom_has_no_tag_requirement(self):
        """freedom-outbound может быть без tag или с tag='direct'."""
        cfg = _cfg_direct()
        ob = cfg["outbounds"][0]
        tag = ob.get("tag", "direct")
        assert tag in ("direct", "freedom", "")


# ── inbound structure ─────────────────────────────────────────────────────────

class TestInboundStructure:
    def test_direct_single_inbound(self):
        cfg = _cfg_direct()
        assert len(cfg["inbounds"]) == 1

    def test_exit_single_inbound(self):
        cfg = _cfg_exit()
        assert len(cfg["inbounds"]) == 1

    def test_direct_no_ws_transport(self):
        """direct использует TCP, не WebSocket — heartbeatPeriod не нужен."""
        cfg = _cfg_direct()
        ss = cfg["inbounds"][0]["streamSettings"]
        assert ss["network"] == "tcp"
        assert "wsSettings" not in ss

    def test_direct_no_heartbeat_on_tcp(self):
        """heartbeatPeriod:30 требуется только на WS inbounds; на TCP — ошибка."""
        cfg = _cfg_direct()
        ss = cfg["inbounds"][0]["streamSettings"]
        assert "heartbeatPeriod" not in ss.get("tcpSettings", {})

    def test_both_configs_have_reality_security(self):
        for cfg in [_cfg_direct(), _cfg_exit()]:
            assert cfg["inbounds"][0]["streamSettings"]["security"] == "reality"


# ── VLESS link routing semantics ──────────────────────────────────────────────

class TestVlessLinkRouting:
    """VLESS-ссылки должны содержать параметры для Reality — клиент применяет routing."""

    _UUID = str(uuid.uuid4())

    def _link(self, host="1.2.3.4"):
        return make_vless_link(self._UUID, host, "PUB", "SID", "sni.ex", "test")

    def test_link_has_reality_security(self):
        assert "security=reality" in self._link()

    def test_link_has_pubkey(self):
        assert "pbk=PUB" in self._link()

    def test_link_has_shortid(self):
        assert "sid=SID" in self._link()

    def test_link_has_flow_vision(self):
        """xtls-rprx-vision обязателен для Reality с TCP."""
        assert "flow=xtls-rprx-vision" in self._link()

    def test_link_type_tcp(self):
        assert "type=tcp" in self._link()

    def test_no_ws_in_direct_link(self):
        """direct-ссылки не используют WebSocket."""
        link = self._link()
        assert "type=ws" not in link
        assert "path=" not in link


# ── googleapis / YouTube list protection ──────────────────────────────────────

class TestYouTubeListProtection:
    """googleapis/gstatic/googleusercontent никогда не должны попасть в списки."""

    FORBIDDEN_IN_YT = [
        "googleapis.com",
        "gstatic.com",
        "googleusercontent.com",
    ]

    def _check_not_in_routing(self, cfg: dict):
        routing_str = json.dumps(cfg.get("routing", {}))
        for domain in self.FORBIDDEN_IN_YT:
            assert domain not in routing_str, \
                f"{domain} найден в routing rules — запрещено"

    def test_direct_config_no_googleapis(self):
        self._check_not_in_routing(_cfg_direct())

    def test_exit_config_no_googleapis(self):
        self._check_not_in_routing(_cfg_exit())


# ── Reality SNI validation ────────────────────────────────────────────────────

class TestRealitySNI:
    def test_sni_propagated_to_dest(self):
        cfg = _cfg_direct(sni="www.apple.com")
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["dest"] == "www.apple.com:443"

    def test_sni_propagated_to_server_names(self):
        cfg = _cfg_direct(sni="www.apple.com")
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert "www.apple.com" in rs["serverNames"]

    def test_exit_sni_propagated(self):
        cfg = _cfg_exit(sni="www.cloudflare.com")
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert "www.cloudflare.com" in rs["serverNames"]

    def test_short_id_in_list(self):
        cfg = _cfg_direct()
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert "SID" in rs["shortIds"]

    def test_show_false(self):
        """show:false — не светим Reality handshake в логах."""
        cfg = _cfg_direct()
        rs = cfg["inbounds"][0]["streamSettings"]["realitySettings"]
        assert rs["show"] is False
