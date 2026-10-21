"""Minimal TMC2209 UART interface for D1.

Uses TMC2209 internal VACTUAL velocity generator (not STEP/DIR).
Wiring: CP2102 TXD --1 kOhm--+-- PDN_UART, CP2102 RXD ---+-- PDN_UART.
Both receive a local echo. Never treat this as closed-loop velocity control.

References: Analog Devices TMC2209 datasheet rev 1.09, registers
GCONF, IFCNT, IOIN, VACTUAL, IHOLD_IRUN, CHOPCONF, DRV_STATUS.
"""
from __future__ import annotations

import math
import time

try:
    import serial
except ImportError:
    serial = None

GCONF, GSTAT, IFCNT, IOIN = 0x00, 0x01, 0x02, 0x06
IHOLD_IRUN, TPOWERDOWN, TPWMTHRS = 0x10, 0x11, 0x13
VACTUAL, CHOPCONF, DRV_STATUS = 0x22, 0x6C, 0x6F
PWMCONF = 0x70

IC_VERSION = 0x21
CHOPCONF_DEFAULT = 0x10000053
VACTUAL_MAX = (1 << 23) - 1
G_PDN_DISABLE = 1 << 6
G_MSTEP_REG_SELECT = 1 << 7
G_MULTISTEP_FILT = 1 << 8
G_EN_SPREADCYCLE = 1 << 2
G_SHAFT = 1 << 3


class DriveError(IOError):
    """UART, driver or operating error."""


def crc8(data: bytes) -> int:
    """TMC UART CRC8; reflected data stream, polynomial x^8+x^2+x+1."""
    crc = 0
    for byte in data:
        for _ in range(8):
            if ((crc >> 7) ^ (byte & 1)) & 1:
                crc = ((crc << 1) ^ 7) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
            byte >>= 1
    return crc


def current_scale(amps: float, rsense: float = 0.110):
    """Return (CS, vsense, actual_rms_A). Default BTT Rsense is 0.110 ohm."""
    if not (0 < amps <= 2) or rsense <= 0:
        raise ValueError("invalid phase RMS current or sense resistor")
    for vsense, vfs in ((1, 0.180), (0, 0.325)):
        cs = round(32 * math.sqrt(2) * amps * (rsense + 0.020) / vfs - 1)
        if cs <= 31:
            cs = max(0, cs)
            real = (cs + 1) * vfs / (32 * (rsense + 0.020) * math.sqrt(2))
            return cs, vsense, real
    raise ValueError("requested current exceeds driver range")


class TMC2209:
    def __init__(self, port=None, *, ser=None, baud=115200, fclk=12e6,
                 rsense=0.110, max_rpm=2500, marker="none", timeout=0.3):
        if ser is None:
            if serial is None:
                raise RuntimeError("pyserial required: pip install -e .")
            if not port:
                raise ValueError("a serial port is required")
            ser = serial.Serial(port, baudrate=baud, timeout=timeout, write_timeout=timeout)
        if marker not in ("none", "rts", "dtr"):
            raise ValueError("marker must be none/rts/dtr")
        self.ser = ser
        self.marker_line = marker
        self.fclk = float(fclk)
        self.rsense = float(rsense)
        self.max_rpm = float(max_rpm)
        self.commanded_rpm = 0.0
        if self.fclk <= 0 or self.max_rpm <= 0:
            raise ValueError("clock and max RPM must be positive")
        self.marker(False)

    def _exchange(self, frame: bytes, answer_size: int = 0) -> bytes:
        self.ser.reset_input_buffer()
        sent = self.ser.write(frame)
        self.ser.flush()
        if sent != len(frame):
            raise DriveError("UART short write")
        echo = self.ser.read(len(frame))
        if echo != frame:
            raise DriveError("UART echo mismatch (check TXD -> 1 kOhm -> PDN_UART and RXD -> PDN_UART)")
        return self.ser.read(answer_size) if answer_size else b""

    def read_reg(self, register: int, retries=3) -> int:
        pkt = bytes((0x05, 0x00, register & 0x7F))
        frame = pkt + bytes((crc8(pkt),))
        last = b""
        for _ in range(retries):
            last = self._exchange(frame, 8)
            if (len(last) == 8 and last[:3] == bytes((0x05, 0xFF, register & 0x7F))
                    and crc8(last[:-1]) == last[-1]):
                return int.from_bytes(last[3:7], "big")
            time.sleep(0.01)
        raise DriveError("no valid reply for register 0x%02X: %s" % (register, last.hex()))

    def write_reg(self, register: int, value: int):
        pkt = bytes((0x05, 0x00, (register & 0x7F) | 0x80)) + (value & 0xFFFFFFFF).to_bytes(4, "big")
        self._exchange(pkt + bytes((crc8(pkt),)))

    def write_checked(self, register: int, value: int):
        before = self.read_reg(IFCNT) & 255
        self.write_reg(register, value)
        after = self.read_reg(IFCNT) & 255
        if after != ((before + 1) & 255):
            raise DriveError("write to 0x%02X not accepted (IFCNT %s -> %s)" %
                             (register, before, after))

    def check_connection(self):
        version = (self.read_reg(IOIN) >> 24) & 0xFF
        if version != IC_VERSION:
            raise DriveError("expected TMC2209 version 0x21, got 0x%02X" % version)
        return version

    def configure(self, irun=0.8, ihold=None, mode="stealth", invert=False,
                  stealth_max_rpm=None):
        """Configure original D1 current/chopper defaults with read-back confirmation."""
        if mode not in ("stealth", "spread"):
            raise ValueError("mode must be stealth or spread")
        if ihold is None:
            ihold = irun  # StealthChop AT#1 standstill tuning
        if ihold > irun:
            raise ValueError("hold current cannot exceed run current")
        self.check_connection()
        self.write_reg(GSTAT, 0x07)  # clear latched status first
        gconf = G_PDN_DISABLE | G_MSTEP_REG_SELECT | G_MULTISTEP_FILT
        if mode == "spread":
            gconf |= G_EN_SPREADCYCLE
        if invert:
            gconf |= G_SHAFT
        self.write_checked(GCONF, gconf)
        cs, vsense, real = current_scale(irun, self.rsense)
        vfs = 0.180 if vsense else 0.325
        cs_hold = max(0, min(31, round(32 * math.sqrt(2) * ihold *
                                    (self.rsense + 0.020) / vfs - 1)))
        chop = (CHOPCONF_DEFAULT & ~(1 << 17)) | (vsense << 17)
        self.write_checked(CHOPCONF, chop)
        self.write_checked(IHOLD_IRUN, cs_hold | (cs << 8) | (4 << 16))
        self.write_checked(TPOWERDOWN, 20)
        threshold = (self.rpm_to_tstep(stealth_max_rpm)
                     if mode == "stealth" and stealth_max_rpm else 0)
        self.write_checked(TPWMTHRS, threshold)
        self.write_checked(VACTUAL, 0)
        self.commanded_rpm = 0.0
        return {"irun_A_actual": round(real, 4), "irun_cs": cs, "ihold_cs": cs_hold,
                "vsense": vsense, "mode": mode, "tpwmthrs": threshold}

    def rpm_to_vactual(self, rpm: float) -> int:
        return round(float(rpm) / 60 * 200 * 256 * (2 ** 24) / self.fclk)

    def vactual_to_rpm(self, v: int) -> float:
        return v * self.fclk * 60 / (200 * 256 * (2 ** 24))

    def rpm_to_tstep(self, rpm: float) -> int:
        if rpm <= 0:
            raise ValueError("threshold rpm must be positive")
        return round(self.fclk / (rpm / 60 * 200 * 256))

    def set_rpm(self, rpm: float):
        if not math.isfinite(rpm) or abs(rpm) > self.max_rpm:
            raise ValueError("rpm outside software limit")
        v = self.rpm_to_vactual(rpm)
        if abs(v) > VACTUAL_MAX:
            raise ValueError("VACTUAL outside signed 24-bit range")
        self.write_reg(VACTUAL, v & 0xFFFFFF)
        self.commanded_rpm = self.vactual_to_rpm(v)
        return v

    def ramp_to(self, rpm: float, accel=100.0, sleep=time.sleep, dt=0.02):
        if accel <= 0:
            raise ValueError("accel must be positive")
        start = self.commanded_rpm
        count = max(1, math.ceil(abs(rpm - start) / (accel * dt)))
        for i in range(1, count + 1):
            self.set_rpm(start + (rpm - start) * i / count)
            sleep(dt)

    def tune_stealthchop(self, sleep=time.sleep, seconds=30.0):
        sleep(0.5)
        self.ramp_to(120, sleep=sleep)
        sleep(seconds)

    def status(self) -> dict:
        g = self.read_reg(GSTAT)
        d = self.read_reg(DRV_STATUS)
        bit = lambda n: bool(d & (1 << n))
        return {"reset": bool(g & 1), "drv_err": bool(g & 2),
                "uv_cp": bool(g & 4), "otpw": bit(0), "ot": bit(1),
                "s2g": bit(2) or bit(3), "s2vs": bit(4) or bit(5),
                "ol": bit(6) or bit(7), "t120": bit(8), "t143": bit(9),
                "t150": bit(10), "t157": bit(11),
                "cs_actual": (d >> 16) & 31, "stealth": bit(30),
                "standstill": bit(31), "drv_status_raw": d, "gstat_raw": g}

    @staticmethod
    def fault(status: dict) -> str | None:
        if status["reset"]:
            return "driver reset: configuration may have been lost"
        if status["drv_err"] or status["ot"]:
            return "driver or thermal fault"
        if status["s2g"] or status["s2vs"]:
            return "motor phase short detected"
        if status["uv_cp"]:
            return "charge-pump undervoltage"
        return None

    def marker(self, on: bool):
        if self.marker_line != "none":
            # Active-low LED: LED anode +3V3 -> 330 ohm -> LED -> RTS/DTR.
            # pyserial "asserted" drives RTS/DTR low on common CP2102 adapters.
            setattr(self.ser, self.marker_line, bool(on))

    def enable(self, on: bool):
        chop = self.read_reg(CHOPCONF)
        self.write_checked(CHOPCONF, (chop & ~15) | (3 if on else 0))

    def stop(self, sleep=time.sleep, accel=200):
        self.ramp_to(0.0, accel=accel, sleep=sleep)
        self.write_reg(VACTUAL, 0)
        self.commanded_rpm = 0.0

    def close(self):
        self.ser.close()


class SimPort:
    """Register-level fake UART for --dry-run and unit tests (NOT motor physics)."""

    def __init__(self):
        self.buf = bytearray()
        self.rts = False
        self.dtr = False
        self.regs = {GCONF: 0x41, GSTAT: 1, IOIN: IC_VERSION << 24,
                     CHOPCONF: CHOPCONF_DEFAULT, DRV_STATUS: 0x80000000,
                     IHOLD_IRUN: 0x1F10, TPOWERDOWN: 20, TPWMTHRS: 0,
                     VACTUAL: 0, PWMCONF: 0xC10D0024}
        self.counter = 0
        self.writes = []

    def reset_input_buffer(self):
        self.buf.clear()

    def flush(self):
        pass

    def write(self, frame: bytes):
        self.buf.extend(frame)  # echoed bus
        if not frame or crc8(frame[:-1]) != frame[-1] or frame[0] != 0x05:
            return len(frame)
        register = frame[2] & 0x7F
        if len(frame) == 8 and frame[2] & 0x80:
            val = int.from_bytes(frame[3:7], "big")
            if register == GSTAT:
                self.regs[GSTAT] &= ~val
            else:
                self.regs[register] = val
            self.counter = (self.counter + 1) & 255
            self.writes.append((register, val))
        elif len(frame) == 4:
            val = self.counter if register == IFCNT else self.regs.get(register, 0)
            if register == DRV_STATUS:
                rotating = bool(self.regs[VACTUAL] & 0xFFFFFF)
                stealth = not bool(self.regs[GCONF] & G_EN_SPREADCYCLE)
                val = (int(not rotating) << 31) | (int(stealth) << 30) | (16 << 16)
            pkt = bytes((0x05, 0xFF, register)) + val.to_bytes(4, "big")
            self.buf.extend(pkt + bytes((crc8(pkt),)))
        return len(frame)

    def read(self, count: int) -> bytes:
        result = bytes(self.buf[:count])
        del self.buf[:count]
        return result

    def close(self):
        pass
