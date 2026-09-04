// ECRIT-HAT firmware -- Arduino Uno R4 WiFi
//
// Potentiostat/galvanostat control for the ECRIT-HAT shield, ported from
// Serial_PSU.
//
// What changed from Serial_PSU:
//   - Current sense moved off A3 (which is not connected on this board) to the
//     INA228 on I2C. calibrateZero() is gone: there is no analog zero to null.
//   - The ADS1115 adds CE, RE, RE-WE and 5 V rail measurement.
//   - Every channel goes through a two-point calibration stored in data flash.
//   - Safety interlocks: over-current, cell-potential window, open cell,
//     comms loss, and a hardware over-current latch on D5.
//   - A missing PSU no longer wedges setup().
//
// Board setup: SJ1-D0 and SJ2-D1, so the PSU is on Serial1 and the USB console
// stays free. That matches the INTERFACE define in KD3000/KD3000.hpp.

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <string.h>
#include <strings.h>

#include "KD3000/KD3000.hpp"

#include "PsuControl.hpp"
#include "Config.hpp"
#include "Calibration.hpp"
#include "Sensors.hpp"
#include "Interlocks.hpp"
#include "CommandParser.hpp"
#include "CalConsole.hpp"
#include "PidController.hpp"
#include "Probe.hpp"

#define Serial_Pi Serial

using namespace EcritHatConfig;

// ---------------------------------------------------------------- state

static BoardCal cal;
static SensorState sensors;
static AdsScanner adsScanner;
static PidController pid;
static PsuState psu;
static CommandReader commandReader;
static CalConsole calConsole;
static InterlockConfig interlockCfg;
static InterlockState interlockState;
static ProbeConfig probeCfg;
static ProbeState probeState;

// the output voltage (V)
static float outputVoltage = DEFAULT_OUTPUT_VOLTAGE;
// the target current (mA) in current mode
static float targetCurrent = DEFAULT_TARGET_CURRENT_MA;

// the status of the system
static bool active = false;
// the mode of the system
static bool currentMode = false;

// Is a KD3005P answering on Serial1? The board is useful without one.
static bool psuPresent = false;
static char psuIdn[64] = {0};

// Bench mode: run the control loop with no supply on the far end. Setpoint
// writes still go out on Serial1, nothing answers, and the comms interlock
// stays quiet because no readback ever succeeded. This is how the interlocks
// and the telemetry path get exercised during bring-up.
static bool dryRun = false;

// Latched trip. Cleared by `w`.
static TripReason latchedTrip = TRIP_NONE;

// 0 = host-compatible CSV, 1 = extended CSV, 2 = Teleplot
static uint8_t telemetryFormat = 0;

// Yellow LED2 on D13: 0 = off, 1 = on, 2 = heartbeat. The heartbeat is the
// default so a glance at the board tells you the loop is still turning.
static uint8_t userLedMode = 2;

// ---------------------------------------------------------------- helpers

static void resetPID() { pid.reset(); }

// The record is the source of truth for the gains; the controller holds a
// working copy. Push after anything that can rewrite the record.
static void applyGainsFromRecord()
{
	pid.kp = cal.pid.kp;
	pid.ki = cal.pid.ki;
	pid.kd = cal.pid.kd;
}

// The output commands need somewhere to send setpoints -- a real supply, or
// dry-run mode for bench work.
static bool psuLinkAvailable() { return psuPresent || dryRun; }

static void printFloatOrNan(float value, uint8_t decimals)
{
	if (isnan(value)) Serial_Pi.print("nan");
	else Serial_Pi.print(value, decimals);
}

// Informational lines must never contain a comma: the host UI treats any line
// with a comma as a telemetry row (SendCommandSerial.py).
static void printLabelled(const char *label, float value, uint8_t decimals, const char *unit)
{
	Serial_Pi.print(label);
	Serial_Pi.print(" = ");
	printFloatOrNan(value, decimals);
	if (unit != nullptr)
	{
		Serial_Pi.print(" ");
		Serial_Pi.print(unit);
	}
	Serial_Pi.println();
}

// LED1 (red, beside CN1) is the output indicator: solid while the output is
// live, flashing on a latched fault, dark otherwise. LED2 (yellow, D13) is the
// user LED and idles as a slow heartbeat.
static void updateLeds(unsigned long nowMs)
{
	bool output;
	if (latchedTrip != TRIP_NONE)
	{
		output = ((nowMs / LED_FAULT_FLASH_MS) % 2) == 0;
	}
	else
	{
		// Probing energises the supply too, and the indicator has to say so.
		output = active || probeIsArmed(probeState);
	}
	digitalWrite(PIN_LED_OUTPUT, output ? HIGH : LOW);

	bool user;
	switch (userLedMode)
	{
		case 0:  user = false; break;
		case 1:  user = true; break;
		default: user = (nowMs % LED_HEARTBEAT_PERIOD_MS) < LED_HEARTBEAT_ON_MS; break;
	}
	digitalWrite(PIN_LED_USER, user ? HIGH : LOW);
}

static void stopOutput()
{
	active = false;
	resetPID();
	setOutput(false);
	interlockState.complianceSinceMs = 0;
}

static void trip(TripReason reason)
{
	latchedTrip = reason;
	stopOutput();

	Serial_Pi.print("TRIP ");
	Serial_Pi.print(tripReasonName(reason));
	if (!isnan(interlockState.offendingValue))
	{
		Serial_Pi.print(" at ");
		Serial_Pi.print(interlockState.offendingValue, 3);
	}
	Serial_Pi.println();

	// The host halts the run when it sees this exact line.
	Serial_Pi.println("Turn off");
}

// ---------------------------------------------------------------- probing

// Every probe reply is this one line, so the motion controller can parse the
// unsolicited contact event and the answer to a poll with the same code.
static void printProbeLine(unsigned long nowMs)
{
	const unsigned long elapsed = (probeState.status == PROBE_ARMED)
		? (nowMs - probeState.startedMs)
		: (probeState.endedMs - probeState.startedMs);

	Serial_Pi.print("PROBE state=");
	Serial_Pi.print(probeStatusName(probeState.status));

	Serial_Pi.print(" current_mA=");
	if (probeState.status == PROBE_CONTACT)
	{
		printFloatOrNan(probeState.contactCurrent_mA, 4);
		Serial_Pi.print(" ce_V=");
		printFloatOrNan(probeState.contactCe_V, 4);
	}
	else
	{
		printFloatOrNan(sensors.current_mA, 4);
	}

	Serial_Pi.print(" elapsed_ms=");
	Serial_Pi.print(probeState.startedMs == 0 ? 0UL : elapsed);
	Serial_Pi.println();
}

// Drop the output and settle into a terminal state. Output first, printing
// second -- the kill should not wait on the serial port.
static void probeFinish(ProbeStatus finalStatus, unsigned long nowMs)
{
	setOutput(false);
	invalidatePsuSetpointCache(psu);
	probeState.status = finalStatus;
	probeState.endedMs = nowMs;
	probeState.consecutive = 0;
	printProbeLine(nowMs);
}

static void probeStart()
{
	if (active)
	{
		Serial_Pi.println("Cannot probe while the output is active. Send f first.");
		return;
	}
	if (latchedTrip != TRIP_NONE)
	{
		Serial_Pi.println("Latched trip. Clear it with w first.");
		return;
	}
	if (!psuLinkAvailable())
	{
		Serial_Pi.println("PSU not Connected");
		return;
	}
	if (!sensors.inaOk)
	{
		Serial_Pi.println("INA228 not available. Contact detection is unavailable.");
		return;
	}

	probeState = ProbeState();
	probeState.status = PROBE_ARMED;
	probeState.startedMs = millis();

	// Current limit before voltage, voltage before output. Never energise into
	// an unknown limit.
	invalidatePsuSetpointCache(psu);
	setPsuCurrentLimitIfNeeded(psu, PSU_CFG, probeCfg.currentLimit_mA / 1000.0f);
	setPsuVoltageIfNeeded(psu, PSU_CFG, probeCfg.volts);
	setOutput(true);

	printProbeLine(probeState.startedMs);
}

static void probeService(unsigned long nowMs)
{
	if (!probeIsArmed(probeState))
	{
		return;
	}

	if ((nowMs - probeState.startedMs) > probeCfg.timeoutMs)
	{
		probeFinish(PROBE_TIMEOUT, nowMs);
		return;
	}

	static unsigned long lastSampleMs = 0;
	if ((nowMs - lastSampleMs) < STEP_MS)
	{
		return;
	}
	lastSampleMs = nowMs;

	readInaFast(sensors, cal);

	if (probeSampleIsContact(probeState, probeCfg, sensors.current_mA))
	{
		// Capture before switching off: once the output drops, so does the
		// evidence.
		probeState.contactCurrent_mA = sensors.current_mA;
		probeState.contactCe_V = sensors.ce_V;
		probeFinish(PROBE_CONTACT, nowMs);
	}
}

static void printProbeConfig()
{
	Serial_Pi.println("--- probe settings ---");
	printLabelled("volts", probeCfg.volts, 3, "V");
	printLabelled("ilim", probeCfg.currentLimit_mA, 3, "mA");
	printLabelled("thresh", probeCfg.threshold_mA, 3, "mA");
	Serial_Pi.print("debounce = ");
	Serial_Pi.print(probeCfg.debounceSamples);
	Serial_Pi.println(" samples");
	Serial_Pi.print("timeout = ");
	Serial_Pi.print(probeCfg.timeoutMs);
	Serial_Pi.println(" ms");
}

// ---------------------------------------------------------------- PID gains

static void printPidGains()
{
	Serial_Pi.print("PID kp = ");
	Serial_Pi.print(pid.kp, 5);
	Serial_Pi.print(" ki = ");
	Serial_Pi.print(pid.ki, 5);
	Serial_Pi.print(" kd = ");
	Serial_Pi.println(pid.kd, 5);
}

static void handlePidCommand(const ParsedCommand &cmd)
{
	if (!cmd.has(1))
	{
		printPidGains();
		return;
	}

	const char *name = cmd.argv[1];

	if (strcasecmp(name, "save") == 0)
	{
		// The record already holds the live gains, so this writes the whole
		// thing -- channel corrections included -- exactly as `save` does
		// inside calibration mode.
		Serial_Pi.println(calSave(cal) ? "Settings saved" : "Settings save FAILED");
		return;
	}

	if (strcasecmp(name, "load") == 0)
	{
		Serial_Pi.println(calLoad(cal) ? "Settings loaded" : "No valid record. Using defaults.");
		applyGainsFromRecord();
		printPidGains();
		return;
	}

	if (strcasecmp(name, "reset") == 0)
	{
		cal.pid = PidGains();
		applyGainsFromRecord();
		resetPID();
		printPidGains();
		Serial_Pi.println("Not saved yet. Send pid save to keep it.");
		return;
	}

	if (!cmd.has(2))
	{
		Serial_Pi.println("Usage: pid <kp|ki|kd> <value>   or   pid save|load|reset");
		return;
	}

	const float value = cmd.number(2);
	if (isnan(value) || fabsf(value) > 1000.0f)
	{
		Serial_Pi.println("Implausible gain. Refused.");
		return;
	}

	// Write the record and the controller together so every save path sees the
	// current value, whichever console the operator used.
	if (strcasecmp(name, "kp") == 0)      cal.pid.kp = value;
	else if (strcasecmp(name, "ki") == 0) cal.pid.ki = value;
	else if (strcasecmp(name, "kd") == 0) cal.pid.kd = value;
	else
	{
		Serial_Pi.print("Unknown gain: ");
		Serial_Pi.println(name);
		return;
	}

	applyGainsFromRecord();
	printPidGains();
	Serial_Pi.println("Not saved yet. Send pid save to keep it.");
}

static void handleProbeCommand(const ParsedCommand &cmd)
{
	if (!cmd.has(1))
	{
		printProbeLine(millis());
		return;
	}

	if (strcasecmp(cmd.argv[1], "start") == 0)
	{
		probeStart();
		return;
	}

	if (strcasecmp(cmd.argv[1], "stop") == 0)
	{
		if (probeIsArmed(probeState))
		{
			probeFinish(PROBE_ABORTED, millis());
		}
		else
		{
			// Nothing was running, so clear the record rather than reporting a
			// stale elapsed time from the previous attempt.
			probeState = ProbeState();
			printProbeLine(millis());
		}
		return;
	}

	if (strcasecmp(cmd.argv[1], "cfg") == 0)
	{
		printProbeConfig();
		return;
	}

	if (strcasecmp(cmd.argv[1], "set") == 0)
	{
		if (!cmd.has(3))
		{
			Serial_Pi.println("Usage: probe set <volts|ilim|thresh|debounce|timeout> <value>");
			return;
		}
		if (probeIsArmed(probeState))
		{
			Serial_Pi.println("Stop the probe before changing its settings.");
			return;
		}

		const char *name = cmd.argv[2];
		const float value = cmd.number(3);

		if (strcasecmp(name, "volts") == 0)
		{
			probeCfg.volts = clampFloat(value, OUTPUT_VOLTAGE_MIN, OUTPUT_VOLTAGE_MAX);
		}
		else if (strcasecmp(name, "ilim") == 0)
		{
			// The shared setpoint path floors the supply current limit at
			// CURRENT_LIMIT_MIN_A, so anything below that would silently become
			// that. Clamp here instead of lying about it.
			probeCfg.currentLimit_mA = clampFloat(value,
			                                      CURRENT_LIMIT_MIN_A * 1000.0f,
			                                      MAX_CURRENT_A * 1000.0f);
		}
		else if (strcasecmp(name, "thresh") == 0)
		{
			probeCfg.threshold_mA = value;
		}
		else if (strcasecmp(name, "debounce") == 0)
		{
			long n = (long)value;
			if (n < 1) n = 1;
			if (n > 255) n = 255;
			probeCfg.debounceSamples = (uint8_t)n;
		}
		else if (strcasecmp(name, "timeout") == 0)
		{
			probeCfg.timeoutMs = (unsigned long)value;
		}
		else
		{
			Serial_Pi.print("Unknown probe setting: ");
			Serial_Pi.println(name);
			return;
		}

		printProbeConfig();
		return;
	}

	Serial_Pi.print("Unknown probe command: ");
	Serial_Pi.println(cmd.argv[1]);
}

// ---------------------------------------------------------------- I2C bring-up

static void initSensors()
{
	Wire.begin();
	Wire.setClock(I2C_CLOCK_HZ);

	// begin() verifies the TI manufacturer ID and the device ID, so a false
	// return means the part is absent or the bus is broken.
	sensors.inaOk = ina.begin(ADDR_INA228, &Wire);
	if (sensors.inaOk)
	{
		configureIna(interlockCfg.inaAlertLimit_A);
	}

	// The ADS1115 has no ID register: begin() only confirms that something
	// acknowledges at 0x48.
	sensors.adsOk = ads.begin(ADDR_ADS1115, &Wire);
	if (sensors.adsOk)
	{
		ads.setDataRate(RATE_ADS1115_128SPS);
		ads.setGain(GAIN_ONE);
	}

	Serial_Pi.print("INA228 ");
	Serial_Pi.println(sensors.inaOk ? "ok" : "NOT FOUND");
	Serial_Pi.print("ADS1115 ");
	Serial_Pi.println(sensors.adsOk ? "ok" : "NOT FOUND");
}

static void i2cScan()
{
	Serial_Pi.println("I2C scan:");
	uint8_t found = 0;
	for (uint8_t address = 1; address < 127; address++)
	{
		Wire.beginTransmission(address);
		if (Wire.endTransmission() == 0)
		{
			Serial_Pi.print("  0x");
			if (address < 16) Serial_Pi.print('0');
			Serial_Pi.println(address, HEX);
			found++;
		}
	}
	if (found == 0)
	{
		Serial_Pi.println("  nothing responded");
	}
}

// ---------------------------------------------------------------- PSU probe

// One *IDN? attempt. Console traffic keeps being serviced by the caller.
static bool probePsuOnce()
{
	char idn[64];
	if (getSerialNumber(idn, sizeof(idn)))
	{
		strncpy(psuIdn, idn, sizeof(psuIdn) - 1);
		psuIdn[sizeof(psuIdn) - 1] = '\0';
		psuPresent = true;
		psu.commsEverOk = true;
		psu.commsOk = true;
		psu.lastGoodCommsMs = millis();
		return true;
	}
	psuPresent = false;
	return false;
}

static void applyPsuBaseline()
{
	setOverCurrentProtection(false);
	setOutput(false);
	invalidatePsuSetpointCache(psu);
	setPsuCurrentLimitIfNeeded(psu, PSU_CFG, MAX_CURRENT_A);
	setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
}

// ---------------------------------------------------------------- reporting

static void printStatus()
{
	Serial_Pi.println("--- status ---");
	Serial_Pi.print("output: ");
	Serial_Pi.println(active ? "on" : "off");
	Serial_Pi.print("mode: ");
	Serial_Pi.println(currentMode ? "constant current" : "constant voltage");
	printLabelled("target current", targetCurrent, 3, "mA");
	printLabelled("commanded voltage", outputVoltage, 3, "V");

	Serial_Pi.print("psu: ");
	if (psuPresent)
	{
		Serial_Pi.println(psuIdn);
		Serial_Pi.print("psu link: ");
		Serial_Pi.println(psu.commsOk ? "ok" : "no reply");
		if (psu.statusValid)
		{
			Serial_Pi.print("psu regulation: ");
			Serial_Pi.println(psu.cvMode ? "CV" : "CC");
			Serial_Pi.print("psu output flag: ");
			Serial_Pi.println(psu.outputOn ? "on" : "off");
		}
		printLabelled("psu readback voltage", psu.voltageReadbackV, 3, "V");
		printLabelled("psu readback current", psu.currentReadbackA, 3, "A");
	}
	else
	{
		Serial_Pi.println("PSU not Connected");
	}

	Serial_Pi.print("dry run: ");
	Serial_Pi.println(dryRun ? "ON - setpoints go nowhere" : "off");
	Serial_Pi.print("INA228: ");
	Serial_Pi.println(sensors.inaOk ? "ok" : "not found");
	Serial_Pi.print("ADS1115: ");
	Serial_Pi.println(sensors.adsOk ? "ok" : "not found");

	Serial_Pi.print("probe: ");
	Serial_Pi.println(probeStatusName(probeState.status));
	Serial_Pi.print("trip: ");
	Serial_Pi.println(tripReasonName(latchedTrip));
	Serial_Pi.print("interlocks: ");
	Serial_Pi.println(interlockCfg.enabled ? "enabled" : "DISABLED");
	Serial_Pi.print("telemetry format: ");
	Serial_Pi.println(telemetryFormat);
	printLabelled("current zero", sensors.zeroCurrent_mA, 4, "mA");
	printLabelled("WE zero", sensors.zeroWe_A, 5, "A");
	Serial_Pi.print("user LED: ");
	Serial_Pi.println(userLedMode == 0 ? "off" : (userLedMode == 1 ? "on" : "heartbeat"));

	Serial_Pi.print("D5 INA alert: ");
	Serial_Pi.println(digitalRead(PIN_INA_ALERT) == LOW ? "asserted" : "idle");
	Serial_Pi.print("D6 ADS alert: ");
	Serial_Pi.println(digitalRead(PIN_ADS_ALERT) == LOW ? "asserted" : "idle");
	Serial_Pi.print("D9 CTS: ");
	Serial_Pi.println(digitalRead(PIN_CTS) == LOW ? "asserted" : "idle");

	printPidGains();
}

static void printMeasurements()
{
	Serial_Pi.println("--- measurements ---");
	if (sensors.adsOk)
	{
		printLabelled("CE  (AIN0)", sensors.ce_V, 4, "V");
		printLabelled("rail (AIN1)", sensors.rail_V, 4, "V");
		printLabelled("RE  (AIN2)", sensors.re_V, 4, "V");
		printLabelled("WE current (AIN3)", sensors.we_A, 4, "A");
		printLabelled("cell RE-WE", sensors.cell_V, 5, "V");
		printLabelled("WE-CE reconstructed", reconstructWeMinusCe(sensors), 4, "V");
	}
	else
	{
		Serial_Pi.println("ADS1115 not available");
	}

	if (sensors.inaOk)
	{
		printLabelled("current", sensors.current_mA, 4, "mA");
		printLabelled("shunt", sensors.shunt_mV, 5, "mV");
		printLabelled("VBUS (CE)", sensors.bus_V, 4, "V");
		printLabelled("power", sensors.power_mW, 3, "mW");
		printLabelled("charge", sensors.charge_C, 4, "C");
		printLabelled("energy", sensors.energy_J, 4, "J");
		printLabelled("die temperature", sensors.dieTemp_C, 2, "C");
	}
	else
	{
		Serial_Pi.println("INA228 not available");
	}
}

static void printLimits()
{
	Serial_Pi.println("--- interlock limits ---");
	Serial_Pi.print("enabled: ");
	Serial_Pi.println(interlockCfg.enabled ? "yes" : "no");
	printLabelled("ocp", interlockCfg.overCurrent_mA, 3, "mA");
	printLabelled("alert", interlockCfg.inaAlertLimit_A, 3, "A");
	printLabelled("cell.lo", interlockCfg.cellWindowLo_V, 4, "V");
	printLabelled("cell.hi", interlockCfg.cellWindowHi_V, 4, "V");
	printLabelled("comp", interlockCfg.compliance_V, 3, "V");
	printLabelled("compi", interlockCfg.complianceMinCurrent_mA, 3, "mA");
	Serial_Pi.print("comphold = ");
	Serial_Pi.print(interlockCfg.complianceHoldMs);
	Serial_Pi.println(" ms");
	Serial_Pi.print("comms = ");
	Serial_Pi.print(interlockCfg.commsTimeoutMs);
	Serial_Pi.println(" ms");
}

static void printHelp()
{
	Serial_Pi.println("Commands:");
	Serial_Pi.println("  c [current_mA] - Hold constant current (mA)");
	Serial_Pi.println("  v [voltage_V] - Hold constant voltage (V)");
	Serial_Pi.println("  r - Reset (output to default voltage)");
	Serial_Pi.println("  f - Turn off output");
	Serial_Pi.println("  z - Capture the live current zero. z 0 clears it. z <mA> sets it");
	Serial_Pi.println("  s - Status");
	Serial_Pi.println("  m - One-shot measurement of every channel");
	Serial_Pi.println("  a - Reset the INA228 charge and energy accumulators");
	Serial_Pi.println("  k - Enter calibration mode");
	Serial_Pi.println("  t [0|1|2] - Telemetry format: host CSV / extended / teleplot");
	Serial_Pi.println("  n - Re-probe the PSU");
	Serial_Pi.println("  w - Clear a latched trip");
	Serial_Pi.println("  u [0|1|2] - Yellow user LED on D13: off / on / heartbeat");
	Serial_Pi.println("  scan - I2C bus scan");
	Serial_Pi.println("  pid - Show gains. pid <kp|ki|kd> <value>. pid save / load / reset");
	Serial_Pi.println("  probe - Contact probe state. probe start / stop / cfg");
	Serial_Pi.println("  probe set <volts|ilim|thresh|debounce|timeout> <value>");
	Serial_Pi.println("  dry [0|1] - Bench mode: run the loop with no PSU attached");
	Serial_Pi.println("  lim - Show interlock limits");
	Serial_Pi.println("  lim on|off - Enable or disable all interlocks");
	Serial_Pi.println("  lim <name> <value> - ocp alert cell.lo cell.hi comp compi comphold comms");
	Serial_Pi.println("  h - Help");
	Serial_Pi.println();
	printPidGains();
}

// ---------------------------------------------------------------- commands

static bool handleLimCommand(const ParsedCommand &cmd)
{
	if (!cmd.has(1))
	{
		printLimits();
		return true;
	}

	if (cmd.is("lim") && strcasecmp(cmd.argv[1], "on") == 0)
	{
		interlockCfg.enabled = true;
		Serial_Pi.println("Interlocks enabled");
		return true;
	}
	if (cmd.is("lim") && strcasecmp(cmd.argv[1], "off") == 0)
	{
		interlockCfg.enabled = false;
		interlockState.complianceSinceMs = 0;
		Serial_Pi.println("Interlocks DISABLED");
		return true;
	}

	if (!cmd.has(2))
	{
		Serial_Pi.println("Usage: lim <name> <value>");
		return true;
	}

	const char *name = cmd.argv[1];
	const float value = cmd.number(2);

	if (strcasecmp(name, "ocp") == 0)            interlockCfg.overCurrent_mA = value;
	else if (strcasecmp(name, "alert") == 0)
	{
		interlockCfg.inaAlertLimit_A = value;
		if (sensors.inaOk) inaSetOvercurrentLimit(value);
	}
	else if (strcasecmp(name, "cell.lo") == 0)   interlockCfg.cellWindowLo_V = value;
	else if (strcasecmp(name, "cell.hi") == 0)   interlockCfg.cellWindowHi_V = value;
	else if (strcasecmp(name, "comp") == 0)      interlockCfg.compliance_V = value;
	else if (strcasecmp(name, "compi") == 0)     interlockCfg.complianceMinCurrent_mA = value;
	else if (strcasecmp(name, "comphold") == 0)  interlockCfg.complianceHoldMs = (unsigned long)value;
	else if (strcasecmp(name, "comms") == 0)     interlockCfg.commsTimeoutMs = (unsigned long)value;
	else
	{
		Serial_Pi.print("Unknown limit: ");
		Serial_Pi.println(name);
		return true;
	}

	printLimits();
	return true;
}

static void handleCommand(const ParsedCommand &cmd)
{
	// Named (multi-character) commands first.
	if (cmd.is("lim"))
	{
		handleLimCommand(cmd);
		return;
	}
	if (cmd.is("scan"))
	{
		i2cScan();
		return;
	}
	if (cmd.is("probe"))
	{
		handleProbeCommand(cmd);
		return;
	}
	if (cmd.is("pid"))
	{
		handlePidCommand(cmd);
		return;
	}
	if (cmd.is("dry"))
	{
		if (cmd.hasArg)
		{
			const bool want = (cmd.arg != 0.0f);
			if (want && psuPresent)
			{
				Serial_Pi.println("A PSU is connected. Dry run refused.");
			}
			else if (active)
			{
				Serial_Pi.println("Turn the output off first.");
			}
			else
			{
				dryRun = want;
			}
		}
		Serial_Pi.print("Dry run ");
		Serial_Pi.println(dryRun ? "on" : "off");
		return;
	}
	if (cmd.is("help"))
	{
		printHelp();
		return;
	}

	switch (cmd.code)
	{
		// constant current mode
		case 'c':
			if (!psuLinkAvailable())
			{
				Serial_Pi.println("PSU not Connected");
				break;
			}
			if (latchedTrip != TRIP_NONE)
			{
				Serial_Pi.println("Latched trip. Clear it with w first.");
				break;
			}
			if (probeIsArmed(probeState))
			{
				Serial_Pi.println("Probe in progress. Send probe stop first.");
				break;
			}
			// Galvanostatic control closes on the INA228. Without it the PID
			// would integrate NaN straight into the setpoint.
			if (!sensors.inaOk)
			{
				Serial_Pi.println("INA228 not available. Constant current is unavailable.");
				break;
			}
			active = true;
			currentMode = true;
			if (cmd.hasArg)
			{
				targetCurrent = cmd.arg;
			}
			resetPID();
			invalidatePsuSetpointCache(psu);
			updateCurrentLimitForTarget(psu, PSU_CFG, targetCurrent);
			setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
			setOutput(true);
			if (!dryRun) updatePsuReadbackIfDue(psu, PSU_CFG, millis(), true);
			Serial_Pi.print("Hold Current target = ");
			Serial_Pi.print(targetCurrent);
			Serial_Pi.println(" mA");
			break;

		// constant voltage mode
		case 'v':
			if (!psuLinkAvailable())
			{
				Serial_Pi.println("PSU not Connected");
				break;
			}
			if (latchedTrip != TRIP_NONE)
			{
				Serial_Pi.println("Latched trip. Clear it with w first.");
				break;
			}
			if (probeIsArmed(probeState))
			{
				Serial_Pi.println("Probe in progress. Send probe stop first.");
				break;
			}
			active = true;
			currentMode = false;
			if (cmd.hasArg)
			{
				outputVoltage = cmd.arg;
			}
			invalidatePsuSetpointCache(psu);
			setPsuCurrentLimitIfNeeded(psu, PSU_CFG, MAX_CURRENT_A);
			setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
			setOutput(true);
			if (!dryRun) updatePsuReadbackIfDue(psu, PSU_CFG, millis(), true);
			Serial_Pi.print("Hold Voltage target = ");
			Serial_Pi.print(outputVoltage);
			Serial_Pi.println(" V");
			break;

		// reset -- the host identifies the board by this exact reply
		case 'r':
			outputVoltage = DEFAULT_OUTPUT_VOLTAGE;
			resetPID();
			if (active)
			{
				setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
			}
			Serial_Pi.println("Reset");
			break;

		// turn off -- the host halts a run on this exact reply
		case 'f':
			if (probeIsArmed(probeState))
			{
				probeFinish(PROBE_ABORTED, millis());
			}
			stopOutput();
			Serial_Pi.println("Turn off");
			break;

		// The INA228 has no analog zero to null the way the old discrete front
		// end did, but it does have an input offset voltage, and the reading at
		// zero current wanders by roughly 0.1 mA as the board warms. Capture it
		// here, in RAM, just before a run.
		case 'z':
			if (active || probeIsArmed(probeState))
			{
				Serial_Pi.println("Cannot zero while active. Turn the output off first.");
				break;
			}

			if (cmd.hasArg)
			{
				if (cmd.arg == 0.0f)
				{
					clearZero(sensors);
				}
				else
				{
					sensors.zeroCurrent_mA = cmd.arg;
				}
			}
			else
			{
				// readRawCalChannel() drives the converter directly, so the
				// scanner has to be out of the way on both sides.
				adsScanner.reset();
				captureZero(sensors, cal, ZERO_SAMPLES);
				adsScanner.reset();
			}

			printLabelled("current zero", sensors.zeroCurrent_mA, 4, "mA");
			printLabelled("WE zero", sensors.zeroWe_A, 5, "A");
			// The host looks for this exact line.
			Serial_Pi.println("Zero calibrated");
			break;

		case 's':
			printStatus();
			break;

		case 'm':
			printMeasurements();
			break;

		case 'a':
			if (sensors.inaOk)
			{
				ina.resetAccumulators();
				sensors.charge_C = 0.0f;
				sensors.energy_J = 0.0f;
				Serial_Pi.println("Accumulators reset");
			}
			else
			{
				Serial_Pi.println("INA228 not available");
			}
			break;

		case 'k':
			if (active || probeIsArmed(probeState))
			{
				Serial_Pi.println("Cannot calibrate while active. Turn the output off first.");
				break;
			}
			calConsole.enter(Serial_Pi, adsScanner);
			break;

		case 't':
			if (cmd.hasArg)
			{
				const int format = (int)cmd.arg;
				telemetryFormat = (uint8_t)((format < 0 || format > 2) ? 0 : format);
			}
			Serial_Pi.print("Telemetry format ");
			Serial_Pi.println(telemetryFormat);
			break;

		case 'n':
			Serial_Pi.println("Probing PSU...");
			if (probePsuOnce())
			{
				Serial_Pi.print("Device: ");
				Serial_Pi.println(psuIdn);
				applyPsuBaseline();
			}
			else
			{
				Serial_Pi.println("PSU not Connected");
			}
			break;

		case 'w':
			if (latchedTrip == TRIP_NONE)
			{
				Serial_Pi.println("No trip latched");
			}
			else
			{
				Serial_Pi.print("Cleared trip ");
				Serial_Pi.println(tripReasonName(latchedTrip));
				latchedTrip = TRIP_NONE;
				sensors.inaAlert = false;
				// Reading DIAG_ALRT clears the latched INA228 flags.
				if (sensors.inaOk) ina.alertFunctionFlags();

				// An open-cell trip leaves the setpoint pinned at the clamp.
				// Resuming from there would just trip again, so start over.
				outputVoltage = DEFAULT_OUTPUT_VOLTAGE;
				resetPID();
				Serial_Pi.print("Setpoint back to ");
				Serial_Pi.print(outputVoltage, 3);
				Serial_Pi.println(" V");
			}
			break;

		case 'u':
			if (cmd.hasArg)
			{
				const int mode = (int)cmd.arg;
				userLedMode = (uint8_t)((mode < 0 || mode > 2) ? 2 : mode);
			}
			Serial_Pi.print("User LED ");
			Serial_Pi.println(userLedMode == 0 ? "off" : (userLedMode == 1 ? "on" : "heartbeat"));
			break;

		case 'h':
			printHelp();
			break;

		default:
			break;
	}
}

// Poll the console once. Returns true if a command was handled.
static bool serviceConsole()
{
	ParsedCommand cmd;
	if (!commandReader.poll(Serial_Pi, cmd))
	{
		return false;
	}

	if (calConsole.handle(cmd, Serial_Pi, cal, sensors, adsScanner))
	{
		// load, erase and clrall all rewrite the record, gains included.
		applyGainsFromRecord();
		return true;
	}

	handleCommand(cmd);
	return true;
}

// ---------------------------------------------------------------- telemetry

static void emitTelemetry()
{
	// readback_V falls back to the commanded value before the first successful
	// readback, which is what the host expects in the third column.
	const float readback = isnan(psu.voltageReadbackV) ? outputVoltage : psu.voltageReadbackV;

	if (telemetryFormat == 2)
	{
		Serial_Pi.print(">current:");
		printFloatOrNan(sensors.current_mA, 4);
		Serial_Pi.print(",voltage:");
		Serial_Pi.print(outputVoltage, 3);
		Serial_Pi.print(",readback_voltage:");
		printFloatOrNan(readback, 3);
		Serial_Pi.print(",cell:");
		printFloatOrNan(sensors.cell_V, 5);
		Serial_Pi.print(",ce:");
		printFloatOrNan(sensors.ce_V, 4);
		Serial_Pi.print(",charge:");
		printFloatOrNan(sensors.charge_C, 4);
		Serial_Pi.println();
		return;
	}

	// Column 1..3 are the contract with SendCommandSerial.py and never move.
	printFloatOrNan(sensors.current_mA, 4);
	Serial_Pi.print(",");
	Serial_Pi.print(outputVoltage, 3);
	Serial_Pi.print(",");
	printFloatOrNan(readback, 3);

	if (telemetryFormat == 1)
	{
		Serial_Pi.print(",");
		printFloatOrNan(sensors.cell_V, 5);
		Serial_Pi.print(",");
		printFloatOrNan(sensors.ce_V, 4);
		Serial_Pi.print(",");
		printFloatOrNan(sensors.re_V, 4);
		Serial_Pi.print(",");
		printFloatOrNan(sensors.charge_C, 4);
		Serial_Pi.print(",");
		printFloatOrNan(sensors.rail_V, 4);
		Serial_Pi.print(",");
		Serial_Pi.print(psu.statusValid ? (psu.cvMode ? "CV" : "CC") : "??");
	}

	Serial_Pi.println();
}

// ---------------------------------------------------------------- setup

void setup()
{
	Serial_Pi.begin(CONSOLE_BAUD);
	Serial1.begin(PSU_BAUD);

	pinMode(PIN_LED_OUTPUT, OUTPUT);
	pinMode(PIN_LED_USER, OUTPUT);
	digitalWrite(PIN_LED_OUTPUT, LOW);
	digitalWrite(PIN_LED_USER, LOW);

	// RN1 supplies the pull-ups, so plain INPUT is right.
	pinMode(PIN_INA_ALERT, INPUT);
	pinMode(PIN_ADS_ALERT, INPUT);

	// The transceiver inverts: LOW on D10 asserts RTS. The KD3005P ignores it,
	// but driving it beats leaving T2IN floating.
	pinMode(PIN_RTS, OUTPUT);
	digitalWrite(PIN_RTS, LOW);
	pinMode(PIN_CTS, INPUT);

	delay(500);

	Serial_Pi.println("ECRIT-HAT Potentiostat Controller");

	if (calLoad(cal))
	{
		Serial_Pi.println("Settings loaded from data flash");
	}
	else
	{
		Serial_Pi.println("No stored settings. Using unity gain and default PID.");
	}
	applyGainsFromRecord();
	printPidGains();

	initSensors();

	// Send OUT0 before anything that can fail or block. If the
	// supply was left on by a previous run and the link is one-way, this is
	// the only thing standing between a live cell and an absent controller.
	setOutput(false);

	for (uint8_t attempt = 0; attempt < PSU_DETECT_ATTEMPTS; attempt++)
	{
		if (probePsuOnce())
		{
			break;
		}

		Serial_Pi.println("PSU not Connected");

		// Keep answering the console while retrying, so the host can still
		// identify the port and calibration still works with no supply.
		const unsigned long waitUntil = millis() + PSU_DETECT_RETRY_MS;
		while ((long)(waitUntil - millis()) > 0)
		{
			serviceConsole();
		}
	}

	if (psuPresent)
	{
		Serial_Pi.print("Device: ");
		Serial_Pi.println(psuIdn);
		applyPsuBaseline();
	}
	else
	{
		Serial_Pi.println("Running without a PSU. Measurement and calibration are available.");
	}

	Serial_Pi.println("Ready");
}

// ---------------------------------------------------------------- loop

void loop()
{
	serviceConsole();

	updateLeds(millis());

	if (calConsole.active())
	{
		return;
	}

	// Probing owns the supply while it is armed, so it runs ahead of anything
	// else and short-circuits the rest of the loop.
	if (probeIsArmed(probeState))
	{
		adsScanner.service(sensors, cal);
		probeService(millis());
		return;
	}

	// Keep the ADS scanner turning whether or not the loop is running, so `m`
	// and the interlocks always have recent numbers.
	adsScanner.service(sensors, cal);

	const unsigned long now = millis();

	// Hardware over-current latch. Open drain, active LOW. Only sampled while
	// the output is on, so a pin left asserted from a previous run cannot trip
	// the next one before it starts.
	if (active && interlockCfg.useInaAlertPin && sensors.inaOk &&
	    digitalRead(PIN_INA_ALERT) == LOW)
	{
		sensors.inaAlert = true;
	}

	static unsigned long lastInaSlowMs = 0;
	if ((now - lastInaSlowMs) >= INA_SLOW_MS)
	{
		lastInaSlowMs = now;
		readInaSlow(sensors, cal);
	}

	if (!active)
	{
		// Still worth a current reading for `m` and for the console.
		static unsigned long lastIdleCurrentMs = 0;
		if ((now - lastIdleCurrentMs) >= STEP_MS)
		{
			lastIdleCurrentMs = now;
			readInaFast(sensors, cal);
		}
		return;
	}

	// Periodic PSU readback for the CSV third field and for comms health.
	// Pointless in dry run: there is nothing on the far end to ask.
	if (!dryRun)
	{
		updatePsuReadbackIfDue(psu, PSU_CFG, millis(), false);
	}

	// Control loop timing
	static unsigned long lastStepMs = 0;
	const unsigned long stepNow = millis();
	if ((stepNow - lastStepMs) < STEP_MS)
	{
		return;
	}
	lastStepMs = stepNow;

	readInaFast(sensors, cal);

	const TripReason reason = checkInterlocks(interlockState, interlockCfg, sensors,
	                                          psu, currentMode, outputVoltage, stepNow);
	if (reason != TRIP_NONE)
	{
		trip(reason);
		return;
	}

	if (currentMode)
	{
		if (isnan(sensors.current_mA))
		{
			// No usable measurement: hold the last setpoint rather than
			// integrating a NaN into it.
			emitTelemetry();
			return;
		}

		const float pidOutput = pid.step(targetCurrent, sensors.current_mA, stepNow, STEP_MS);
		outputVoltage += pidOutput;
		outputVoltage = clampFloat(outputVoltage, OUTPUT_VOLTAGE_MIN, OUTPUT_VOLTAGE_MAX);

		updateCurrentLimitForTarget(psu, PSU_CFG, targetCurrent);
		setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
	}
	else
	{
		setPsuCurrentLimitIfNeeded(psu, PSU_CFG, MAX_CURRENT_A);
		setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
	}

	emitTelemetry();
}

