# ECRIT-HAT calibration

Bench procedure for the seven correction channels. The firmware applies
`corrected = gain * raw + offset` per channel and keeps the record in the RA4M1's
data flash, so it survives both power cycles and reflashing the sketch.

The same record also carries the PID gains — see [Control gains](#control-gains--pid)
at the end. One `save` writes both.

⚠️ **The record has a layout version, and bumping it discards what was stored.**
Adding a field shifts every offset after it, so old records are rejected rather
than misread. If you change the struct, write your existing gains and offsets
down first — `list` prints all of them — and re-apply them with `set` afterwards.

Connect at 9600 baud, 8N1. `k` enters calibration mode; `x` leaves it. The
control loop is suspended for the whole session and nothing reaches flash until
you type `save`.

## Channels

| Name | Source | Unit | Reference needed |
|---|---|---|---|
| `ce` | AIN0, CE via the 220k/33k divider and MCP6002-B | V | 25–30 V source + DMM |
| `re` | AIN2, RE via MCP6002-A | V | 2–4 V source + DMM |
| `cell` | AIN2 − AIN3 differential | V | 2–4 V across CN4 and CN2 |
| `we` | AIN3, shunt tap | A | 4–5 A through the shunt |
| `rail` | AIN1, 5 V rail via 10k/10k | V | DMM at TP7, or INA228 VBUS |
| `inai` | INA228 `CURRENT` | mA | 4–5 A series reference |
| `inav` | INA228 `VBUS` | V | 25–30 V source + DMM |

## Commands

```
k                        enter calibration mode
list                     gain, offset, live raw and corrected for every channel
raw <chan>               averaged uncorrected and corrected reading
avg [n]                  samples averaged per reading (1-64, default 16)

lo <chan> <reference>    record the low point
hi <chan> <reference>    record the high point
fit <chan>               solve gain and offset from the two points
one <chan> <reference>   single-point gain only, offset forced to zero
set <chan> <g> <o>       write gain and offset directly

clr <chan> / clrall      back to unity gain and zero offset
save / load / erase      the data flash record
x                        leave calibration mode
```

Points recorded by `lo` and `hi` live in RAM and are lost on reset. If a jumper
move resets the board — it can, if you brush the 5 V rail — write the raw numbers
down, compute the fit by hand, and apply it with `set`. The arithmetic is:

```
g = (x2 - x1) / (y2 - y1)
o = x1 - g * y1
```

where `x` is the reference and `y` is what `raw` reported.

The firmware rejects a fit whose gain lands outside ±1000 or whose two points are
too close to separate. That is deliberate: it catches the common mistake of
recording both points under the same stimulus.

## Order of work

Do `rail` and `inav` first. Both are cheap, and once `inav` is trusted it becomes
an on-board voltmeter you can use as the reference for `ce`.

### 1. `rail` — 5 V monitor

Single point is enough; the offset is negligible next to a gain error of about
0.5%.

The honest way is to reference it against `inav` rather than a DMM snapshot,
because a USB-powered rail wanders several millivolts and a DMM reading taken
minutes apart from an ADC reading is not the same measurement. Jumper CN1 to TP7
so both channels watch the same net, then interleave:

```
k
avg 64
raw rail        note the raw value
raw inav        note the raw value
```

Repeat three times, average the ratio `inav_raw / rail_raw`, and apply it:

```
set rail <ratio> 0
save
```

Consecutive ratios should agree to about 0.01%. If they scatter more than that,
something is drifting faster than you can measure it.

Without the CN1 jumper, `one rail <dmm reading>` works too, but take the DMM
reading and the console reading within a few seconds of each other.

### 2. `inav` — INA228 VBUS

Usually needs nothing. VBUS has no divider and converts against an internal
reference; on the board measured here it read within 1 mV of a DMM at 4.6 V, and
TI specs its gain error at ±0.05% up to 85 V. Calibrating it against a reference
no better than itself only injects noise.

Check it, don't correct it: apply a known voltage to CN1, `raw inav`, and confirm
agreement. Only fit it if you find a real disagreement at 25–30 V.

### 3. `ce` — counter electrode, 0 to 31.4 V

```
k
avg 64
lo ce 0.0            with CN1 shorted to GND
hi ce <dmm volts>    with CN1 on a 25-30 V source
fit ce
raw ce               sanity check against the DMM
save
```

Use the full range. A fit taken over the bottom few volts still gives a usable
gain — reference uncertainty enters proportionally, so ±2 mV on 4.6 V is 0.043%,
which is ±13 mV at 30 V — but it cannot see nonlinearity or near-rail buffer
behaviour, which is exactly what a 6.5× extrapolation would expose.

Expect the offset to dominate. On the board measured here the divider ratio was
right to 0.08% after offset removal, while the offset itself was 15.3 mV referred
to CN1, which is 2.0 mV at the buffer output — ordinary MCP6002 input offset
voltage, inside its ±4.5 mV spec.

Verify the low end afterwards. With CN1 open the corrected reading should sit
within a millivolt or two of zero.

### 4. `re` and `cell` — reference electrode, 0 to 4.096 V

```
lo re 0.0            CN4 shorted to GND
hi re <dmm volts>    CN4 on a 2-4 V source
fit re
```

`cell` is the AIN2 − AIN3 hardware differential, so calibrate it with the DMM
across CN4 and CN2, not against ground:

```
lo cell 0.0          CN4 and CN2 shorted together
hi cell <dmm volts>
fit cell
```

Leave CN4 open and `re` floats to roughly half the analog rail, which pushes
`cell` past the GAIN_TWO full scale and pins it at 2.048 V. That is an open
input, not a fault, but it does mean the `cell` interlock window will trip if you
arm it with nothing attached.

### 5. `inai` and `we` — current, 0 to 5 A

Both need real current through the shunt. **Do not connect a supply directly to
CN2**: the shunt is 8 mΩ to ground, so anything without a current limit is a dead
short.

Drive it from the PSU through a load that sets the current, with a reference
meter in series:

```
PSU+ ── load ── [reference meter] ── CN2 (Cathode)
PSU- ─────────────────────────────── CN3 (Ground)
```

Take the zero with the source disconnected, then the high point at 4–5 A:

```
lo inai 0
hi inai <reference mA>
fit inai
lo we 0
hi we <reference A>
fit we
save
```

**Calibrate these at amps, not milliamps.** Two things go wrong at low current:

- `we` reads the shunt tap through AIN3 at GAIN_SIXTEEN, 7.8 µV per LSB. At 21 mA
  the signal is 167 µV and the channel's own offset was 29 mA-equivalent and
  drifting by ±1.5 mA. The offset completely swamps it.
- `inai` agrees with a handheld DMM to about 0.5% at 21 mA, which is inside the
  combined uncertainty of the DMM's mA range (±0.5–1%) and the shunt's tolerance
  (±1%). There is no resolvable gain error to correct at that level — fitting one
  is fitting noise.

Shunt resistance error is a pure gain error, identical at 20 mA and 5 A, so a
low-current fit is not wrong in principle. It is just that no low-current
reference is good enough to determine it.

## Mechanical zero — `probe`

Finding the anode/cathode contact point, so the motion platform knows what
"zero distance" means. Done dry, with no solution in the cell.

The current path is the ordinary plating one, metal instead of solution:

```
PSU+ -> anode -> [contact] -> cathode -> CN2 -> shunt -> CN3 -> PSU-
```

CN1 does not carry it. That terminal is a high-impedance sense tap, so the
detector is the INA228, not the CE voltage. Dry, the gap is air and the current
is genuinely zero; on contact it goes to the supply's current limit. Against the
±0.1 mA noise floor that is a 100:1 step.

```
probe                       state, as one parseable line
probe start                 set the limit, set the voltage, energise, watch
probe stop                  abort and switch off
probe cfg                   show settings
probe set <name> <value>    volts | ilim | thresh | debounce | timeout
```

Every reply is the same shape, so the host parses the unsolicited contact event
and the answer to a poll with identical code:

```
PROBE state=armed current_mA=0.0488 elapsed_ms=1630
PROBE state=contact current_mA=9.8734 ce_V=0.0421 elapsed_ms=12400
PROBE state=timeout current_mA=-0.0293 elapsed_ms=60001
PROBE state=aborted current_mA=0.0684 elapsed_ms=4908
```

The state **latches**. The firmware emits the contact line the moment it fires,
but a host that misses it still sees `state=contact` on its next poll, so the
motion loop can be a simple step-then-ask.

### Host sequence

1. `z` — capture the live zero, so the 1 mA threshold means something.
2. `probe start` — the supply comes up at 1 V with a 10 mA limit.
3. Step the anode down 0.1 mm.
4. Send `probe`. If the reply says `state=contact`, stop: that position is
   mechanical zero. If it says `state=armed`, loop back to 3.
5. `probe stop` when done, or after a `timeout`.

The firmware kills the output itself on contact — before it prints anything, so
the shutdown never waits on the serial port. The host does not need to react
fast, or at all.

### Settings

| Setting | Default | Notes |
|---|---|---|
| `volts` | 1.0 V | Open-circuit probe voltage. See the warning below |
| `ilim` | 10 mA | Supply current limit. Floored at `CURRENT_LIMIT_MIN_A` |
| `thresh` | 1.0 mA | 10× the noise floor, 1/10th of the limit |
| `debounce` | 2 | Consecutive samples over threshold, 50 ms apart |
| `timeout` | 60000 ms | Switch off if contact never arrives |

⚠️ **Keep `volts` low.** The supply's output capacitance dumps into the contact
the instant metal meets metal, and that energy goes as V² — roughly 0.2 mJ at
1 V, but 6 mJ at 5 V for a few hundred microfarads. Firmware cannot help: the
discharge is over in microseconds, long before any sample. The only lever is the
voltage setting, and the cathode surface you are about to plate is what pays for
a spark. Raise `volts` only if oxide is genuinely blocking detection, and raise
it a little at a time.

Guards, all enforced both ways: probing refuses to start while a run is active
or a trip is latched, and `c`, `v`, `k` and `z` all refuse while probing. `f`
aborts a probe as well as stopping a run. LED1 is lit throughout, because the
supply really is energised.

### If detection is unreliable

Surface oxide on the cathode raises contact resistance. At 1 V, a 1 kΩ contact
gives exactly the 1 mA threshold and a 10 kΩ contact is missed entirely. In
order of preference: clean the surfaces, lower `thresh` toward 0.5 mA (still
5× the noise), then raise `volts`. Raising `ilim` does not help detection at
all — the limit only caps the current *after* contact — and it makes any spark
worse.

### A gentler alternative, for a future board revision

Probing through the supply means probing through its output capacitance. A spare
GPIO wired to CN1 through a series resistor would let the MCU do continuity
detection on its own — internal pull-up high when open, pulled low through the
shunt on contact, at something like 125 µA and no bulk capacitance at all. That
is thousands of times gentler than any PSU-based probe and needs no supply.

It is not wired on Rev A, and it needs protection: CN1 sees up to 30 V during a
real run, so a direct GPIO connection would destroy the pin. It wants a series
resistor small enough to keep the logic threshold usable but large enough to
survive the fault, which is a genuine design trade-off rather than a jumper wire.
Worth considering for the next board spin; D7 and D8 are both free.

## The live zero — `z`

Separate from the stored calibration, and the thing you will use most often.

```
z          capture the present zero for inai and we
z 0        clear it
z <mA>     set the current zero by hand
```

The reading at zero current is not zero and does not stay put. On the board
measured here, 64-sample averages ranged from −0.19 mA to +0.06 mA over half an
hour, with `readShuntVoltage()` agreeing at about −1.25 µV. Part is INA228 input
offset; the drift on top is thermoelectric EMF across the shunt terminals as the
board warms — normal for a low-side shunt.

Because the drift is as large as the offset, a value in flash is stale within the
hour. `z` holds its result in RAM only and it expires on reset, which is the
point: a zero captured cold is worthless once the board is warm.

**Capture it immediately before a run, at working temperature, with the cell
disconnected.** With a cell attached and the output merely off, open-circuit
galvanic current still flows through the shunt, and zeroing then would silently
absorb it as the new origin. The firmware never re-zeros automatically for that
reason, and `z` refuses while the output is active.

For `we` this matters enormously — it removes an offset larger than a 21 mA
signal. For `inai` it is marginal: residual noise after `INA228_COUNT_16`
averaging is about ±0.1 mA, already larger than the offset.

## Control gains — `pid`

The PID gains live in the same data flash record as the channel corrections, so
a tuned loop survives a reflash. They are set outside calibration mode, because
tuning happens while the loop is actually running:

```
pid                   show kp, ki, kd
pid kp <value>        set one gain, effective immediately
pid ki <value>
pid kd <value>
pid save              commit the whole settings record to data flash
pid load              reload it, discarding unsaved edits
pid reset             back to the compiled defaults (0.01, 0, 0)
```

Changes take effect the moment you type them but stay in RAM until `pid save`.
The command says so every time, because tuning a loop and then losing it to a
reset is an easy way to waste an afternoon. `save` inside calibration mode writes
the same record, so either route persists both halves.

Gains outside ±1000 and NaN are refused, and a stored record that somehow
contains one falls back to defaults on load.

**Tune with kp alone.** In the incremental form the controller uses, kp is
already summed into the output every step, so it behaves as an integral gain.
Setting ki non-zero adds a *second* integrator and will oscillate. The shipped
`ki = kd = 0` is a deliberate choice, not an unfinished one. Retune by stepping
the target 10 %, raising kp until the current just begins to overshoot, then
backing off by about a third.

## Checks that need no reference

Worth running after any change, since none of them need a calibrated source:

- `scan` — 0x40 and 0x48 must both acknowledge.
- `m` with nothing attached — CE near 0 V, VBUS near 0 V, RE floating near half
  rail, current within about ±0.1 mA of zero.
- `shunt` should equal 8 mΩ × current whenever you are injecting a known current.
- Reset the accumulators with `a`, wait a known time under steady current, and
  confirm `charge` ÷ elapsed matches `current`. This catches a scaling error in
  `readCharge()`, which is the number that maps to plated mass.
- Continuity between TP1 (GND) and TP2 (AGND) through R12, and TP8 (AVDD) equal
  to TP7 (5 V) — the ferrite has no DC drop, so any difference means a problem.
