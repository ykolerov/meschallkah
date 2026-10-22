# Wiring — current FT232 / TMC2209 test assembly

**Observed working on 22 October 2026:** FT232 USB–UART on COM4 and BIGTREETECH TMC2209 v1.3 returned IOIN version 0x21. The motor also rotated under software control. This does **not** certify soldering quality, protection circuitry, full operating envelope, or the newly assembled board.

## Electrical wiring (power OFF during assembly)

| FT232 USB–UART | TMC2209 v1.3 | Condition |
|---|---|---|
| VCC set to **3.3 V** | VIO | Measure VCC under load; never send 5 V to VIO |
| GND | GND (logic), common with DC supply minus | Shared **downstream-of-USB-isolator** ground |
| TXD through **1 kΩ** | J1-4 PDN_UART | Single-wire half-duplex UART |
| RXD direct | **same** J1-4 PDN_UART | RX sees command echo |
| RTS | LED cathode (optional) | LED anode via **100 Ω** to 3.3 V; intended wiring, not yet end-to-end verified |
| CTS | not connected | |

These names must be checked against **physical silkscreen**. On BTT 2209 v1.3 J1-5 is an alternate UART pad on some module configurations. Do not use it without confirming the module routing.

| Other connection | Wire |
|---|---|
| Laboratory DC supply positive | LM2596S-ADJ module IN+ |
| Laboratory DC supply negative | LM2596S-ADJ module IN− |
| LM2596S-ADJ OUT+ | TMC2209 VM (J2-1) |
| LM2596S-ADJ OUT− | TMC2209 power GND (J2-2) |
| 100 µF / 35 V electrolytic plus/minus | directly across VM/GND, polarity observed |
| Additional ceramic decoupling | VM/GND close to driver, value to be confirmed |
| A-phase measured coil pair | A1/A2 (J2-4/J2-3) |
| B-phase measured coil pair | B1/B2 (J2-5/J2-6) |
| MS1 and MS2 | GND; address 0 |
| CLK, STEP, DIR | GND; VACTUAL uses internal generator |
| EN | 10 kΩ resistor to 3.3 V, normally open pushbutton to GND |

**EN is active-low**: button released means driver OFF; button held means driver enabled. Unlike a latching SPDT switch, the momentary button does **not** keep the motor enabled when released. This exact pushbutton configuration has not been electrically inspected here. 10 kΩ at 3.3 V draws **0.33 mA** when pressed, not microamps.

FT232 RTS for synchronization: the above 100 Ω resistor is the **as-built intended component**, not a generally validated universal LED resistor. Check actual LED type, continuous current, FT232 RTS sink-current limit and output polarity before enabling. For an unknown or high-power LED, use a transistor switch with its own suitably rated supply and resistor; do not drive it directly from RTS. To test with USB only, choose the RTS output via pyserial and measure LED response; program-controlled camera sync still unverified.

## Power and protection limitations

The actual supply chain is **lab supply → LM2596S-ADJ buck → capacitor across VM/GND → TMC2209**, with FT232 supplying separate 3.3 V logic. The LM2596S is a regulator, **not a fail-safe overvoltage disconnect**. It needs sufficient input headroom above its 24 V setting; the module's capacitors and inductor may have lower voltage/current ratings than the IC. Measure module input/output under load and examine all component ratings before operating at 24 V. Do not turn up the laboratory PSU to compensate for a misconfigured regulator.

Using an ADuM-based USB isolator is planned: **PC → USB hub → isolator → FT232**. Confirm that this particular isolator isolates USB *power and data* and can supply FT232 + VIO. Never bridge isolation barrier grounds elsewhere.

The StepperOnline 17HE15-1504S is not the original motor; identify winding pairs by resistance measurements, never by wire color alone. No live motor disconnects. Connect/disconnect with lab supply OFF, USB disconnected, and capacitors discharged.

## Safe power-up sequence

1. Power OFF, disconnect USB; inspect solder joints, diode/capacitor orientation and mechanical retention.
2. Verify no short VM–GND, that coil A and coil B are separate pairs and no external conductor touches the board.
3. Power FT232 via USB isolator. Measure approx. 3.3 V at VIO.
4. With **EN released (OFF)**, turn on lab supply with appropriate voltage/current limits. Measure LM2596 output **at VM/GND** before a motion command.
5. Run `python sweep.py check --port COM4` (replace COM4 with actual port). No `--rpm` means no motion command.
6. Before motion, securely mount motor and guard any rotor. A momentary EN pushbutton must be held for motor operation; released EN disables power stage.

The power supply and motor can remain energized after a PC or USB failure. Software shutdown and a human-operated button are **not** an autonomous fail-safe.
