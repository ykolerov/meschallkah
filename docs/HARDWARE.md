# Hardware: baseline design versus current assembly

The reference specification is **D1_build_instructions.pdf v1.0 (13 Oct 2026)** for IYPT 2027 Problem 10 “Air vortex”. The table distinguishes that *design* from the actual equipment described and partially tested on 22 Oct 2026.

| Component | Original specification | Current prototype |
|---|---|---|
| Motor | NEMA17 17HS4401, 200 steps/rev, 1.5 A, 1.5 Ω, 2.8 mH | **StepperOnline 17HE15-1504S**, 1.5 A, 200 steps/rev, ~2.3 Ω, ~4 mH (nominal product specifications; verify motor label and coil resistance) |
| Driver | BIGTREETECH TMC2209 V1.3 | **Same** |
| USB–UART | CP2102, 3.3 V | **FTDI FT232**, 3.3 V selected; CP2102 remains software-compatible |
| Motor supply | 24 V ≥2 A enclosed supply | Laboratory DC supply → **LM2596S-ADJ buck module** → VM; voltage under new wiring **not yet documented by measurement** |
| Logic supply | 3.3 V from USB adapter | 3.3 V from FT232 VCC |
| Supply capacitor | 100 µF ≥35 V, close to VM/GND | Electrolytic + ceramic decoupling planned/soldered; exact values and verification still to be recorded |
| TX resistor | 1 kΩ | Intended 1 kΩ TX-to-PDN_UART connection |
| Enable | Latching SPDT GND/VIO | **Momentary pushbutton EN→GND, 10 kΩ pullup to 3.3 V** |
| Camera sync LED | LED + 330 Ω via RTS | Intended LED + **100 Ω** via FT232 RTS; functional verification pending |
| USB isolation | Not in original BOM | ADuM USB isolator on hand, actual model/power separation unverified |

**Measured on the earlier working wiring:** COM4 returned TMC2209 version `0x21`, IRUN 0.7955 A RMS, no driver error/thermal fault, motor rotated. Laboratory supply was reported at **17 V, ~100–150 mA input** during one set of no-load tests. Input current is not motor winding RMS current.

### Tachometer observations (earlier test setup)

| Setpoint | Laser tachometer DT2234C Plus |
|---|---|
| 200 rpm | 201.3 rpm |
| 500 rpm | 503 rpm |
| 1000 rpm | 1005–1006 rpm |

These imply approximately **+0.5–0.65%**, consistent with clock scaling error; tachometer accuracy, sampling, thermal drift and repeatability remain unverified. An approximate fitted calibration from these *reported* values should not be represented as a certified calibration for the newly soldered board. Re-measure at operating voltage and temperature.

### Mechanical design still to build

PETG disc Ø60 × 8 mm, 5 mm D shaft hub and M3 set screw or flange coupler; two NdFeB blocks 20 × 10 × 5 mm of opposite polarity; magnet center spacing initially 0.8× stir-bar length (32 mm for 40 mm bar). Magnet retention **must be mechanical**, not adhesive alone. Add a guard around the rotor before high-speed tests.

Motor mount on vibration damping, separate ~200×200×3 mm acrylic vessel support on four M6 rods with rubber washers, ~300×300×18 mm plywood/MDF base, 4 rubber feet. Nominal magnet-to-bar gap 6–8 mm **not yet validated**.

### Acceptance criteria (still unverified)

Original target: 50–2000 rpm, ≤1 rpm command increments, ≤0.5% short-term stability, >8 mN·m at 1500 rpm and negligible surface vibration. None is fully established by the current no-load measurements. See [commissioning](COMMISSIONING.md).

**Do not run the drive unattended.** A stalled or disconnected USB link does not automatically remove TMC2209 motor power. Keep motor supply current limited and an accessible hardware OFF.
