"""D1 magnetic-stirrer control: check, make-table, run, fit-clock.

No microcontroller: PC -> CP2102 USB-UART -> TMC2209 VACTUAL.
The output is the *commanded* speed, not the measured bar speed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import sys
import time
from pathlib import Path

from tmc2209_uart import DriveError, SimPort, TMC2209
from port_discovery import resolve_port


def drive_options(parser):
    parser.add_argument("--port", help="optional override; default auto-detect CP210x and verify TMC2209")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--dry-run", action="store_true", help="simulate register I/O, no motor")
    parser.add_argument("--fclk", type=float, default=12e6, help="effective calibrated TMC clock in Hz")
    parser.add_argument("--rsense", type=float, default=0.110)
    parser.add_argument("--irun", type=float, default=0.8, help="phase current, RMS A")
    parser.add_argument("--ihold", type=float, default=None)
    parser.add_argument("--mode", choices=("stealth", "spread"), default="stealth")
    parser.add_argument("--stealth-max-rpm", type=float, default=None,
                        help="optional mode-transition rpm; normally keep one mode")
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--max-rpm", type=float, default=2500.0)
    parser.add_argument("--accel", type=float, default=100.0, help="rpm per second")
    parser.add_argument("--marker", choices=("none", "rts", "dtr"), default="none",
                        help="only choose rts/dtr if the output is physically wired")
    parser.add_argument("--marker-invert", action="store_true",
                        help="invert electrical assertion of a physically connected marker")


def open_drive(args):
    port = args.port
    if not args.dry_run and not port:
        port = resolve_port(baud=args.baud)
    driver = TMC2209(
        port=port, ser=SimPort() if args.dry_run else None,
        baud=args.baud, fclk=args.fclk, rsense=args.rsense,
        max_rpm=args.max_rpm, marker=args.marker)
    sleep = (lambda seconds: time.sleep(seconds * 0.001)) if args.dry_run else time.sleep
    return driver, sleep


def configure(driver, args):
    return driver.configure(irun=args.irun, ihold=args.ihold, mode=args.mode,
                            invert=args.invert, stealth_max_rpm=args.stealth_max_rpm)


def critical_check(driver):
    state = driver.status()
    failure = driver.fault(state)
    if failure:
        raise DriveError(failure)
    return state


def cmd_check(args):
    driver, sleep = open_drive(args)
    try:
        print("TMC version 0x%02X" % driver.check_connection())
        print("configuration:", configure(driver, args))
        print("status:", critical_check(driver))
        if args.rpm:
            if args.mode == "stealth":
                print("StealthChop initial tuning: 0.5s stationary + 30s at 120 rpm")
                driver.tune_stealthchop(sleep=sleep)
            driver.ramp_to(args.rpm, accel=args.accel, sleep=sleep)
            sleep(args.seconds)
            print("status at commanded rpm:", critical_check(driver))
        print("check completed; rpm shown is a setpoint, not a tachometer reading")
    finally:
        safe_shutdown(driver, sleep, args.accel, args.marker_invert)


def safe_shutdown(driver, sleep, accel=100, marker_off=False):
    """Attempt software stop; **cannot** protect against USB/PC connection loss."""
    try:
        try:
            driver.marker(marker_off)
        finally:
            driver.stop(sleep=sleep, accel=max(200.0, accel))
            driver.enable(False)
    except Exception as e:
        print("WARNING: software stop not confirmed (%s). Switch physical EN OFF NOW." % e,
              file=sys.stderr)
        raise
    finally:
        driver.close()


def read_table(path):
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for line in csv.reader(fh):
            if not line or not line[0].strip() or line[0].lstrip().startswith("#"):
                continue
            if line[0].strip().lower() == "rpm":
                continue
            if len(line) != 3:
                raise ValueError("each CSV row must have rpm,wait_s,record_s")
            values = tuple(float(s) for s in line)
            if any(not math.isfinite(v) for v in values) or values[1] < 0 or values[2] <= 0:
                raise ValueError("invalid step values: " + str(values))
            out.append(values)
    if not out:
        raise ValueError("empty step table")
    return out


class Logger:
    FIELDS = ("iso_time", "elapsed_s", "step", "phase", "rpm_commanded",
              "vactual", "stealth", "cs_actual", "otpw", "t120", "ol",
              "standstill", "gstat", "drv_status", "note")

    def __init__(self, path, metadata):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = open(self.path, "w", newline="", encoding="utf-8")
        for value in metadata:
            self.stream.write("# " + value + "\n")
        self.writer = csv.DictWriter(self.stream, fieldnames=self.FIELDS)
        self.writer.writeheader()
        self.started = time.monotonic()

    def log(self, step, phase, drive, state=None, note=""):
        row = {
            "iso_time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            "elapsed_s": "%.3f" % (time.monotonic() - self.started),
            "step": step, "phase": phase,
            "rpm_commanded": "%.4f" % drive.commanded_rpm,
            "vactual": drive.rpm_to_vactual(drive.commanded_rpm),
            "note": note,
        }
        if state:
            for key in ("stealth", "cs_actual", "otpw", "t120", "ol", "standstill"):
                row[key] = state[key]
            row["gstat"] = "%08X" % state["gstat_raw"]
            row["drv_status"] = "%08X" % state["drv_status_raw"]
        self.writer.writerow(row)
        self.stream.flush()

    def close(self):
        self.stream.close()


def poll(driver, logger, index, phase, duration, every, sleep):
    count = math.ceil(duration / every)
    for item in range(count):
        state = driver.status()
        logger.log(index, phase, driver, state)
        reason = driver.fault(state)
        if reason:
            raise DriveError(reason)
        if state["otpw"]:
            print("WARNING: driver temperature pre-warning; monitor/stop experiment",
                  file=sys.stderr)
        sleep(min(every, duration - item * every))


def cmd_run(args):
    table = read_table(args.table)
    if args.poll <= 0:
        raise ValueError("--poll must be positive")
    if any(abs(rpm) > args.max_rpm for rpm, _, _ in table):
        raise ValueError("a table rpm exceeds --max-rpm")
    driver, sleep = open_drive(args)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = args.log or ("D1_log_" + stamp + ".csv")
    logger = None
    try:
        cfg = configure(driver, args)
        logger = Logger(filename, [
            "D1 sweep; driver TMC2209; motor 17HS4401; dry_run=%s" % args.dry_run,
            "table=%s fclk_Hz=%s accel_rpm_s=%s" % (args.table, args.fclk, args.accel),
            "configuration=%s marker=%s" % (cfg, args.marker),
            "rpm_commanded is NOT observed speed; measure stir bar by video"])
        driver.marker(bool(args.marker_invert))  # idle marker state, including inverted wiring
        print("Log:", filename, ";", len(table), "steps")
        logger.log(-1, "start", driver, critical_check(driver))
        if args.mode == "stealth" and not args.no_tune:
            print("StealthChop tuning...")
            driver.tune_stealthchop(sleep=sleep)
            logger.log(-1, "tuned", driver, critical_check(driver))
        for index, (rpm, wait_s, record_s) in enumerate(table):
            print("[%s/%s] command %.2f rpm" % (index + 1, len(table), rpm))
            logger.log(index, "ramp", driver, note="target=%s" % rpm)
            driver.ramp_to(rpm, accel=args.accel, sleep=sleep)
            logger.log(index, "ramp_end", driver, critical_check(driver))
            poll(driver, logger, index, "settle", wait_s, args.poll, sleep)
            on = not args.marker_invert
            if args.marker != "none":
                driver.marker(on)
            try:
                logger.log(index, "record_start", driver, note="marker=%s" % args.marker)
                poll(driver, logger, index, "record", record_s, args.poll, sleep)
            finally:
                if args.marker != "none":
                    driver.marker(not on)
                logger.log(index, "record_end", driver)
        logger.log(len(table), "complete", driver)
        print("Completed all steps.")
    except BaseException as ex:
        if logger is not None:
            logger.log(-1, "abort", driver, note=type(ex).__name__ + ": " + str(ex))
        raise
    finally:
        try:
            safe_shutdown(driver, sleep, args.accel, args.marker_invert)
        finally:
            if logger is not None:
                logger.close()


def make_values(lo, hi, center, fine_width, fine, coarse, down=True):
    if not (0 < lo < hi and center > 0 and 0 < fine <= 1 and 0 < coarse <= 1
            and 0 < fine_width < 1):
        raise ValueError("invalid range or step percentages")
    seq = []
    rpm = lo
    while rpm < hi:
        seq.append(round(rpm, 3))
        is_fine = abs(rpm - center) <= fine_width * center
        rpm *= 1 + (fine if is_fine else coarse)
    seq.append(round(hi, 3))
    if down:
        seq.extend(seq[-2::-1])
    return seq


def cmd_make_table(args):
    if args.wait < 0 or args.record <= 0:
        raise ValueError("wait must be >=0, record >0")
    values = make_values(args.lo, args.hi, args.center, args.fine_width,
                         args.fine, args.coarse, down=not args.no_down)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        fh.write("# D1 speed sequence: initial coarse/fine then optional down sweep\n")
        writer = csv.writer(fh)
        writer.writerow(("rpm", "wait_s", "record_s"))
        for rpm in values:
            writer.writerow((rpm, args.wait, args.record))
    print("%s: %s steps, %.1f minutes + ramps" %
          (args.out, len(values), len(values) * (args.wait + args.record) / 60))


def fit_clock(command, measured, nominal=12e6):
    if len(command) < 2 or len(command) != len(measured):
        raise ValueError("at least 2 paired measurements required")
    if not all(math.isfinite(v) and v > 0 for v in command + measured):
        raise ValueError("speeds must be finite and positive")
    k = sum(x * y for x, y in zip(command, measured)) / sum(x * x for x in command)
    residuals = [y - k * x for x, y in zip(command, measured)]
    stderr = math.sqrt(sum(r * r for r in residuals) /
                       ((len(command) - 1) * sum(x * x for x in command)))
    return k, nominal * k, stderr, residuals


def cmd_fit_clock(args):
    if args.fclk <= 0:
        raise ValueError("invalid nominal clock")
    k, eff, err, residuals = fit_clock(args.cmd, args.meas, args.fclk)
    print("ratio n_measured / n_commanded = %.8f +/- %.8f" % (k, err))
    print("effective fclk = %.2f Hz; set --fclk %.2f" % (eff, eff))
    for rpm, e in zip(args.cmd, residuals):
        print("command %8.2f rpm; fit residual %+.4f rpm" % (rpm, e))


def main(argv=None):
    parser = argparse.ArgumentParser(description="IYPT D1 TMC2209 drive")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="test UART and optionally spin")
    drive_options(p)
    p.add_argument("--rpm", type=float, default=0.0)
    p.add_argument("--seconds", type=float, default=10.0)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("run", help="run an rpm,wait_s,record_s CSV schedule")
    drive_options(p)
    p.add_argument("--table", required=True)
    p.add_argument("--log")
    p.add_argument("--poll", type=float, default=1.0)
    p.add_argument("--no-tune", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("make-table", help="generate up/down speed schedule")
    p.add_argument("--lo", type=float, required=True)
    p.add_argument("--hi", type=float, required=True)
    p.add_argument("--center", type=float, required=True)
    p.add_argument("--fine-width", type=float, default=0.25)
    p.add_argument("--fine", type=float, default=0.02)
    p.add_argument("--coarse", type=float, default=0.08)
    p.add_argument("--wait", type=float, default=120)
    p.add_argument("--record", type=float, default=10)
    p.add_argument("--no-down", action="store_true")
    p.add_argument("--out", default="steps.csv")
    p.set_defaults(func=cmd_make_table)

    p = sub.add_parser("fit-clock", help="fit oscillator from commanded and measured rpm")
    p.add_argument("--fclk", type=float, default=12e6)
    p.add_argument("--cmd", nargs="+", type=float, required=True)
    p.add_argument("--meas", nargs="+", type=float, required=True)
    p.set_defaults(func=cmd_fit_clock)
    try:
        args = parser.parse_args(argv)
        args.func(args)
        return 0
    except (DriveError, ValueError, OSError) as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Confirm physical EN=OFF.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
