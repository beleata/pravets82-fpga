"""Protocol validation without a connected Pico or FPGA."""
import importlib.util
from pathlib import Path
import sys
import types
import io
import json

import pytest


@pytest.fixture
def bridge(monkeypatch):
    class Pin:
        IN, OUT = 0, 1
        pins = {}
        def __init__(self, number, direction, value=0):
            self.state = value
            self.number = number
            self.pins[number] = self
        def value(self, value=None):
            if value is not None:
                self.state = value
            return self.state
    monkeypatch.setitem(sys.modules, "machine", types.SimpleNamespace(Pin=Pin))
    path = Path(__file__).resolve().parents[1] / "pico" / "bridge.py"
    spec = importlib.util.spec_from_file_location("a2_bridge_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.physical_transfer = module.transfer
    module.Pin = Pin
    module.calls = []
    def transfer(data):
        module.calls.append(data)
        return bytes(reversed(data))
    module.transfer = transfer
    return module


@pytest.mark.parametrize("line", [
    "not json", "[]", "null", '{}', '{"id":true,"tx":"10"}',
    '{"id":-1,"tx":"10"}', '{"id":1,"tx":""}',
    '{"id":1,"tx":"0"}', '{"id":1,"tx":"gg"}',
    '{"id":1,"tx":" 1"}', '{"id":1,"tx":12}',
    '{"id":1,"tx":"' + "00" * 8195 + '"}',
])
def test_invalid_requests_never_touch_spi(bridge, line):
    assert "error" in bridge.handle(line)
    assert bridge.calls == []


def test_valid_request_preserves_id_and_bytes(bridge):
    assert bridge.handle('{"id":82,"tx":"a501FF"}') == {
        "id": 82, "rx": "ff01a5", "irq": 0}
    assert bridge.calls == [bytes.fromhex("a501ff")]


def test_maximum_payload(bridge):
    response = bridge.handle('{"id":1,"tx":"' + "a5" * 8194 + '"}')
    assert response["rx"] == "a5" * 8194
    assert len(bridge.calls[0]) == 8194


def test_gpio_master_samples_high_and_preserves_bit_order(bridge, monkeypatch):
    monkeypatch.setattr(bridge.time, "sleep_us", lambda _: None, raising=False)
    outgoing = bytes.fromhex("308001a5")
    incoming = bytes.fromhex("00813c5a")
    response_bits = iter((byte >> bit) & 1 for byte in incoming for bit in range(7, -1, -1))
    observed_mosi = []
    original_value = bridge.Pin.value

    def value(pin, new=None):
        if pin.number == 21 and new is None:
            assert bridge.sck.state == 1
            assert bridge.cs.state == 0
            return next(response_bits)
        if pin.number == 20 and new == 1:
            assert bridge.cs.state == 0
            observed_mosi.append(bridge.mosi.state)
        return original_value(pin, new)

    monkeypatch.setattr(bridge.Pin, "value", value)
    assert bridge.physical_transfer(outgoing) == incoming
    assert observed_mosi == [(byte >> bit) & 1 for byte in outgoing for bit in range(7, -1, -1)]
    assert (bridge.cs.state, bridge.sck.state, bridge.mosi.state) == (1, 0, 0)


def test_gpio_master_releases_bus_on_read_failure(bridge, monkeypatch):
    monkeypatch.setattr(bridge.time, "sleep_us", lambda _: None, raising=False)
    original_value = bridge.Pin.value

    def value(pin, new=None):
        if pin.number == 21 and new is None:
            raise OSError("simulated input failure")
        return original_value(pin, new)

    monkeypatch.setattr(bridge.Pin, "value", value)
    with pytest.raises(OSError):
        bridge.physical_transfer(b"\xa5")
    assert (bridge.cs.state, bridge.sck.state, bridge.mosi.state) == (1, 0, 0)


def test_oversize_line_is_drained_before_next_request(bridge, monkeypatch, capsys):
    class Input(io.StringIO):
        def readline(self, size=-1):
            line = super().readline(size)
            if not line:
                raise EOFError("test complete")
            return line
    request = '{"id":2,"tx":"1234"}\n'
    stream = Input("x" * (bridge.MAX_LINE + 100) + "\n" + request)
    monkeypatch.setattr(bridge.sys, "stdin", stream)
    with pytest.raises(EOFError):
        bridge.main()
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert replies == [{"id": None, "error": "line too long"},
                       {"id": 2, "rx": "3412", "irq": 0}]
    assert bridge.calls == [bytes.fromhex("1234")]
