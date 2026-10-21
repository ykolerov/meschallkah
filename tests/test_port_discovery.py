"""Tests for read-only CP210x -> TMC2209 serial-port discovery."""
from types import SimpleNamespace

import pytest

import port_discovery as ports
import sweep


def fake_port(name, *, vid=None, pid=None, description="serial", product=None):
    return SimpleNamespace(
        device=name, vid=vid, pid=pid, description=description,
        product=product, manufacturer=None, hwid=None,
    )


def cp(name):
    return fake_port(name, vid=0x10C4, pid=0xEA60,
                     description="Silicon Labs CP210x USB to UART Bridge")


def test_matching_by_usb_ids_or_cp210x_name_not_generic_usb_serial():
    assert ports.is_cp210x(cp("COM5"))
    assert ports.is_cp210x(fake_port("COM2", description="CP2102 Bridge"))
    assert not ports.is_cp210x(fake_port("COM1", description="USB Serial"))
    assert not ports.is_cp210x(fake_port("COM6", vid=0x0403, pid=0x6001,
                                       description="FTDI USB Serial"))


def test_single_verified_adapter_auto_selected_only_correct_port_is_probed():
    seen, messages = [], []
    devices = [fake_port("COM2", description="Generic adapter"), cp("COM8"), cp("COM5")]
    def probe(device):
        seen.append(device)
        return device == "COM8"
    result = ports.resolve_port(comports=devices, probe=probe, output_fn=messages.append)
    assert result == "COM8"
    assert seen == ["COM5", "COM8"]  # stable ordering
    assert "0x21" in messages[-1]


def test_no_usb_adapter_does_not_probe_any_port():
    used = []
    with pytest.raises(ValueError, match="No CP210x"):
        ports.resolve_port(comports=[fake_port("COM2")],
                           probe=lambda p: used.append(p))
    assert used == []


def test_unresponsive_driver_informative_error():
    with pytest.raises(ValueError, match="24 V VM"):
        ports.resolve_port(comports=[cp("COM3")],
                           probe=lambda p: (_ for _ in ()).throw(OSError("busy")))


def test_multiple_verified_ports_interactive_selection():
    choices = iter(["wrong", "2"])
    msgs = []
    port = ports.resolve_port(
        comports=[cp("COM6"), cp("COM3")], probe=lambda p: True,
        interactive=True, input_fn=lambda message: next(choices),
        output_fn=msgs.append,
    )
    assert port == "COM6"
    assert "Invalid choice." in msgs


def test_multiple_verified_ports_noninteractive_needs_port():
    with pytest.raises(ValueError, match=r"Specify --port.*COM3.*COM7"):
        ports.resolve_port(
            comports=[cp("COM7"), cp("COM3")], probe=lambda p: True,
            interactive=False,
        )


def test_probe_only_reads_version_and_always_closes(monkeypatch):
    calls = []
    class FakeDriver:
        def __init__(self, *, port, baud, marker, timeout):
            calls.append(("open", port, baud, marker, timeout))
        def check_connection(self):
            calls.append(("read_version",))
            return 0x21
        def close(self):
            calls.append(("close",))
    monkeypatch.setattr(ports, "TMC2209", FakeDriver)
    assert ports.probe_tmc2209("COM7") is True
    assert [c[0] for c in calls] == ["open", "read_version", "close"]


def test_failed_probe_also_closes(monkeypatch):
    calls = []
    class BrokenDriver:
        def __init__(self, **kwargs):
            pass
        def check_connection(self):
            raise OSError("no reply")
        def close(self):
            calls.append("closed")
    monkeypatch.setattr(ports, "TMC2209", BrokenDriver)
    with pytest.raises(OSError):
        ports.probe_tmc2209("COM10")
    assert calls == ["closed"]


def test_manual_port_bypasses_autodiscovery(monkeypatch):
    monkeypatch.setattr(sweep, "resolve_port",
                        lambda **kwargs: (_ for _ in ()).throw(AssertionError("probed")))
    class FakeDriver:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
    monkeypatch.setattr(sweep, "TMC2209", FakeDriver)
    args = SimpleNamespace(
        port="COM11", baud=115200, dry_run=False, fclk=12e6,
        rsense=.11, max_rpm=2500, marker="none",
    )
    driver, _ = sweep.open_drive(args)
    assert driver.kwargs["port"] == "COM11"


def test_run_without_port_resolves_first(monkeypatch):
    used = []
    monkeypatch.setattr(sweep, "resolve_port",
                        lambda **kwargs: used.append(kwargs) or "COM9")
    class FakeDriver:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
    monkeypatch.setattr(sweep, "TMC2209", FakeDriver)
    args = SimpleNamespace(
        port=None, baud=57600, dry_run=False, fclk=12e6,
        rsense=.11, max_rpm=2500, marker="none",
    )
    driver, _ = sweep.open_drive(args)
    assert driver.kwargs["port"] == "COM9"
    assert used == [{"baud": 57600}]


def test_dry_run_never_scans_real_usb_ports(monkeypatch):
    monkeypatch.setattr(sweep, "resolve_port",
                        lambda **kwargs: (_ for _ in ()).throw(AssertionError("scanned real ports")))
    assert sweep.main(["check", "--dry-run"]) == 0
