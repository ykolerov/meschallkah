import pytest

from tmc2209_uart import (TMC2209, SimPort, crc8,
                           current_scale, VACTUAL)


def test_uart_crc_from_datasheet_example():
    assert crc8(bytes.fromhex("05 00 06")) == 0x6F


def test_current_default_is_approximately_0_8_amp():
    cs, vsense, amps = current_scale(0.8, 0.110)
    assert (cs, vsense) == (25, 1)
    assert amps == pytest.approx(0.7954, abs=0.003)


def test_sim_driver_config_speed_and_stop():
    port = SimPort()
    d = TMC2209(ser=port)
    assert d.check_connection() == 0x21
    config = d.configure()
    assert config["mode"] == "stealth"
    for rpm in (50, 600, 2000, -60):
        d.set_rpm(rpm)
        assert d.commanded_rpm == pytest.approx(rpm, abs=0.002)
    assert d.status()["reset"] is False
    d.stop(sleep=lambda _: None)
    assert port.regs[VACTUAL] == 0
    d.enable(False)
    d.close()


def test_sim_status_modes():
    d = TMC2209(ser=SimPort())
    d.configure(mode="spread")
    assert d.status()["stealth"] is False


def test_marker_optional_and_dtr():
    port = SimPort()
    d = TMC2209(ser=port, marker="dtr")
    assert port.dtr is False
    d.marker(True)
    assert port.dtr is True
    d.marker(False)
    assert port.dtr is False


def test_too_fast_and_current_outside_limit():
    d = TMC2209(ser=SimPort())
    d.configure()
    with pytest.raises(ValueError):
        d.set_rpm(3000)
    with pytest.raises(ValueError):
        current_scale(9)
    with pytest.raises(ValueError):
        d.configure(ihold=1.0)


def test_reset_is_fault():
    d = TMC2209(ser=SimPort())
    assert d.fault(d.status()) is not None
    d.configure()
    assert d.fault(d.status()) is None
