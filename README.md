# meschallkah — D1 magnetic-stirrer drive for IYPT 2027

Programmable NEMA17 magnetic-stirrer drive for Problem 10 “Air vortex”, setup S1. Windows + Python + TMC2209 single-wire UART, camera-speed calibration and CSV sweep logging.

## Project state (22 Oct 2026)

**Prototype tested, not commissioned.** UART communications with the real BIGTREETECH TMC2209 V1.3 succeeded on COM4; chip reported `0x21`. A StepperOnline motor rotated at commanded speeds of 200, 500 and 1000 rpm. The new soldered power/control assembly, camera sync LED, guard, magnet rotor and full experiments **have not been independently verified**. Passing Python tests does not prove hardware reliability.

[Actual hardware and original BOM](docs/HARDWARE.md) · [Wiring / power](docs/WIRING.md) · [Commissioning, tests, examples](docs/COMMISSIONING.md) · [Sources](docs/SOURCES.md).

### Main electronics

- **StepperOnline 17HE15-1504S** NEMA17 (original spec used 17HS4401); BIGTREETECH **TMC2209 V1.3**.
- **FTDI FT232** USB–UART adapter, 3.3 V logic; the previous CP2102 remains supported. UART: FT232 TX through 1 kΩ to PDN_UART; FT232 RX directly to **same** PDN_UART (single wire).
- Laboratory DC supply → **LM2596S-ADJ** buck → motor VM; 100 µF ≥35 V electrolytic and ceramic decoupling. 3.3 V VIO from FT232, common downstream ground. Optional ADuM USB isolator.
- **EN** active-low: momentary button to GND and 10 kΩ pull-up to 3.3 V; motor enabled **while button is held**.
- Optional camera synchronization: FT232 **RTS** LED (100 Ω currently planned); test electrical drive current and polarity before connecting it. The sync LED does not record video.

## Windows installation

Clone at `E:\meschallkah`:

~~~powershell
Set-Location E:\
git clone https://github.com/ykolerov/meschallkah.git
Set-Location E:\meschallkah
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[video,dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\sweep.py check --dry-run
~~~

If already cloned, run `git pull` from `E:\meschallkah`. The existing project virtual environment is independent of ESP-IDF. Full software installation script: `scripts/setup.ps1`.

## Check connected hardware without rotating

When all wiring and voltages are verified and EN is **released/OFF**:

~~~powershell
.\.venv\Scripts\python.exe .\sweep.py check --port COM4
~~~

The software also auto-discovers a compatible FT232/CP210x port and verifies TMC2209 version `0x21` when `--port` is omitted. `COM4` is the observed historical port, not a permanent assignment. No `--rpm` means no spin command.

## Motion tests

Only after safe mechanical mounting and power checks:

~~~powershell
# A short diagnostic run without the extra 30-second StealthChop tune:
.\.venv\Scripts\python.exe .\sweep.py check --port COM4 --rpm 200 --seconds 10 --mode spread --invert

# Or keep StealthChop but explicitly skip its 30-second tuning for diagnostics:
.\.venv\Scripts\python.exe .\sweep.py check --port COM4 --rpm 200 --seconds 10 --no-tune
~~~

Without `--no-tune`, `check --rpm` in StealthChop mode first tunes ~30 seconds at 120 rpm, **in addition** to requested `--seconds` and ramp time. For quantitative runs, follow the manufacturer's StealthChop tuning procedure or choose SpreadCycle consistently.

~~~powershell
.\.venv\Scripts\python.exe .\sweep.py make-table --lo 200 --hi 1500 --center 700 --out steps.csv
.\.venv\Scripts\python.exe .\sweep.py run --port COM4 --table steps.csv --fclk 12000000
~~~

`12000000` is a **nominal** reference, not actual oscillator calibration. Use `fit-clock` and `disc_rate.py` for speed measurements. Current reported tachometer observations are recorded in [hardware](docs/HARDWARE.md).

## Safety / limits

**Never disconnect motor with VM powered.** Buck regulator and capacitors do **not** constitute guaranteed overvoltage protection. Verify the actual regulator board voltage rating, output voltage and polarity before connecting VM. A single-wire UART test does not validate motor-output safety. Do not leave this open-loop drive running unattended: loss of PC/USB does **not** guarantee motor stop. Mechanical retention and guarded enclosure required for magnet rotor operation.
