# meschallkah — D1 programmable magnetic-stirrer drive

Python control and build instructions for the **D1 drive** of IYPT 2027 Problem 10 (“Air vortex”), setup S1.

**Scope:** follows the component selection in *D1_build_instructions.pdf*, v1.0 (13 October 2026). No motor, driver, PSU, or control-architecture substitutions. This repository concerns the drive, not a complete vortex-imaging system.

**Status: SIMULATION ONLY. HARDWARE NOT BUILT, CALIBRATED, OR ACCEPTED.** A commanded rpm is not a measured rpm.

## Components

- NEMA17 **17HS4401**, 1.8°/step; **BIGTREETECH TMC2209 v1.3**; 24 V ≥ 2 A enclosed DC power supply.
- USB–TTL **FTDI FT232 USB–UART adapter** (current hardware, use 3.3 V logic and verify VCC with a meter). The earlier CP2102 remains supported. **Never connect +5 V to VIO.**
- Two NdFeB magnets 20 × 10 × 5 mm, PETG disc, acrylic platform, physical EN/off switch, 100 µF 35 V capacitor, 1 kΩ TX resistor.
- Optional sync LED + 330 Ω via FT232 RTS, if wired and verified. Default remains **no sync LED**.

See [parts and mechanics](docs/HARDWARE.md) and [pin-to-pin wiring](docs/WIRING.md) before connecting power.

## Windows quick start (no hardware)

If you prefer one-command Windows setup, run:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\simulate.ps1
~~~

These scripts do **not** touch physical COM ports or energize the drive.

Requires Python **3.10 or newer**.

~~~powershell
git clone https://github.com/ykolerov/meschallkah.git
cd meschallkah
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[video,dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe sweep.py check --dry-run
.\.venv\Scripts\python.exe sweep.py make-table --lo 200 --hi 1500 --center 700 --out steps.csv
.\.venv\Scripts\python.exe sweep.py run --dry-run --table examples\smoke.csv
~~~

To connect **only after** [commissioning](docs/COMMISSIONING.md):

~~~powershell
# The drive is wired and powered, with hardware EN=OFF.
.\.venv\Scripts\python.exe sweep.py check

# Only after the wiring check, guard and motor tests: EN=RUN.
.\.venv\Scripts\python.exe sweep.py check --rpm 120 --seconds 60
.\.venv\Scripts\python.exe sweep.py run --table steps.csv --fclk 12000000
~~~

**Automatic COM-port discovery is now the default** for `check` and `run`. It searches **FTDI FT232** USB–UART adapters (typically VID:PID `0403:6001`) and CP210x adapters (typically `10C4:EA60`), then verifies that a TMC2209 responds with chip version `0x21` using a **read-only** UART request. If one passes, it is selected automatically. If multiple pass, choose from the numbered menu; noninteractive runs must specify a port. If none pass, the program stops with a wiring/24 V troubleshooting message. Probe needs **both 3.3 V logic and 24 V VM** to be connected; it does not energize the motor or change TMC registers.

To override auto-detection or use a different USB–UART adapter:

~~~powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
.\.venv\Scripts\python.exe sweep.py check --port COM5
.\.venv\Scripts\python.exe sweep.py run --port COM5 --table steps.csv --fclk 12000000
~~~

The 12 MHz clock is **nominal**; calibrate with fit-clock before data collection. `--dry-run` never scans or opens physical ports.

## Operations

| Command | Function |
| --- | --- |
| sweep.py check | Verify IC version 0x21, configure driver, read faults, optional short spin |
| sweep.py make-table | Up/down rpm schedule: coarse 8%, fine 2% near threshold |
| sweep.py run | Ramp, settle, record, CSV log with status and timestamps |
| sweep.py fit-clock | Calibrate effective driver oscillator from video measurements |
| disc_rate.py | Measure observed disc rpm from brightness transitions in a video ROI |

For LED synchronization select **--marker rts** or **--marker dtr** only after wiring the corresponding output. Without the extra wire omit --marker: rotation and logging still work. For video analysis run: python disc_rate.py video.mp4 --roi X Y W H --fps 239.76.

## Limits and safety

- TMC2209 VACTUAL is **open-loop**. Motor step loss or stir-bar decoupling is not reliably detected by the driver. Measure actual stir-bar speed from the S1 video.
- **Loss of USB/PC control may leave the motor turning.** Do not run unattended before an independent hardware failsafe has been implemented and verified. Keep the physical EN/off switch accessible; turn it OFF to stop. Python exception handling is not an emergency stop.
- 2000–2500 rpm torque, temperature, vibration, 6–8 mm coupling gap are all **unverified**. Pass T1–T9 before scientific measurements.
- Mechanically **retain and enclose** the spinning magnets. Do not rely only on glue for containment.
- The video helper only measures periodic rotation; it does **not** reconstruct the vortex surface.

Documentation: [hardware](docs/HARDWARE.md) · [wiring](docs/WIRING.md) · [commissioning](docs/COMMISSIONING.md) · [sources](docs/SOURCES.md).

Based on *D1_build_instructions.pdf*, 2026-10-13. Registers checked against the [TMC2209 datasheet rev. 1.09](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2209_datasheet_rev1.09.pdf); module pinout against [BIGTREETECH](https://github.com/bigtreetech/docs/blob/master/docs/TMC2209.md).
