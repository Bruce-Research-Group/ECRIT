#include <Arduino.h>
#include "KD3000/KD3000.hpp"
#include "CommandParser.hpp"
#include "CurrentSense.hpp"
#include "PidController.hpp"
#include "PsuControl.hpp"

#include "Config.hpp"

#define Serial_Pi Serial
#define Serial_PSU Serial1

static CurrentSenseState currentSense;
static PidController pid;
static PsuState psu;
static CommandReader commandReader;
static float lastMeasuredCurrent_mA = 0.0f;

// the output voltage (V)
float outputVoltage = 0.5f;
// the argument value from the serial command
float argumentValue = 0.0f;
// the target current (mA) in current mode
float targetCurrent = 10.0f;

// the status of the system
bool active = false;
// the mode of the system
bool currentMode = false;

using namespace SerialPsuConfig;

static void resetPID() { pid.reset(); }

static void handleCommand(const ParsedCommand &cmd)
{
	switch (cmd.code)
	{
		// constant current mode
		case 'c':
			active = true;
			currentMode = true;
			if (cmd.hasArg)
			{
				targetCurrent = cmd.arg;
			}
			resetPID();
			updateCurrentLimitForTarget(psu, PSU_CFG, targetCurrent);
			setOutput(true);
			updatePsuReadbackIfDue(psu, PSU_CFG, millis(), true);
			Serial_Pi.print("Hold Current, target = ");
			Serial_Pi.print(targetCurrent);
			Serial_Pi.println(" mA");
			break;

		// constant voltage mode
		case 'v':
			active = true;
			currentMode = false;
			if (cmd.hasArg)
			{
				outputVoltage = cmd.arg;
			}
			setPsuCurrentLimitIfNeeded(psu, PSU_CFG, MAX_CURRENT);
			setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
			setOutput(true);
			updatePsuReadbackIfDue(psu, PSU_CFG, millis(), true);
			Serial_Pi.print("Hold Voltage, target = ");
			Serial_Pi.print(outputVoltage);
			Serial_Pi.println(" V");
			break;

		// reset
		case 'r':
			outputVoltage = 0.5f;
			resetPID();
			if (active)
			{
				setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
			}
			Serial_Pi.println("Reset");
			break;

		// turn off
		case 'f':
			active = false;
			resetPID();
			setOutput(false);
			Serial_Pi.println("Turn off");

			delay(500); // wait for analog readings to stabilize
			calibrateZero(currentSense, CURRENT_SENSE_CFG);
			Serial_Pi.println("Zero calibrated");
			break;

		case 'p':
			if (cmd.hasArg) pid.kp = cmd.arg;
			break;

		case 'i':
			if (cmd.hasArg) pid.ki = cmd.arg;
			break;

		case 'd':
			if (cmd.hasArg) pid.kd = cmd.arg;
			break;

		case 'z':
			if (!active)
				Serial_Pi.println("Calibrating zero...");
			else
			{
				Serial_Pi.println("Cannot calibrate zero while active. Please turn off first.");
				break;
			}

			delay(500); // wait for analog readings to stabilize
			calibrateZero(currentSense, CURRENT_SENSE_CFG);
			Serial_Pi.println("Zero calibrated");
			break;

		case 'h':
			// help command
			Serial_Pi.println("Commands:");
			Serial_Pi.println("  c [current_mA] - Hold constant current (mA)");
			Serial_Pi.println("  v [voltage_V] - Hold constant voltage (V)");
			Serial_Pi.println("  r - Reset (output to default voltage)");
			Serial_Pi.println("  f - Turn off output");
			Serial_Pi.println("  p [kp] - Set PID proportional gain");
			Serial_Pi.println("  i [ki] - Set PID integral gain");
			Serial_Pi.println("  d [kd] - Set PID derivative gain");
			Serial_Pi.println("  z - Calibrate zero (turn off output first)");
			Serial_Pi.println("  h - Help");
			Serial_Pi.println();
			Serial_Pi.println("Current PID parameters:");
			Serial_Pi.print("  kp: ");
			Serial_Pi.print(pid.kp, 4);
			Serial_Pi.print(", ki: ");
			Serial_Pi.print(pid.ki, 4);
			Serial_Pi.print(", kd: ");
			Serial_Pi.println(pid.kd, 4);
			break;

		default:
			break;
	}
}

void setup() {
	Serial_Pi.begin(9600);
	Serial_PSU.begin(9600);
	delay(500);

	pinMode(LED_BUILTIN, OUTPUT);
	pinMode(CURRENT_PIN, INPUT);
	analogReadResolution(ADC_RESOLUTION_BITS);

	Serial_Pi.println("Serial PSU Controller");

	char idn[64];
	if (getSerialNumber(idn, sizeof(idn))) {
		Serial_Pi.print("Device: ");
		Serial_Pi.println(idn);
	} else {
		Serial_Pi.println("Device query failed");
		while (1) {}
	}

	setOverCurrentProtection(false);
	setOutput(false);
	setPsuCurrentLimitIfNeeded(psu, PSU_CFG, MAX_CURRENT);
	setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);

	delay(500); // wait for analog readings to stabilize
	calibrateZero(currentSense, CURRENT_SENSE_CFG);
	Serial_Pi.println("Zero calibrated");
}

void loop() {
	// Handle serial commands
	ParsedCommand cmd;
	if (commandReader.poll(Serial_Pi, cmd))
	{
		handleCommand(cmd);
	}

	// Update status LED.
	digitalWrite(LED_BUILTIN, active);

	if (!active)
	{
		return;
	}

	// Periodic PSU readback for the CSV 3rd field.
	updatePsuReadbackIfDue(psu, PSU_CFG, millis(), false);

	// Control loop timing
	static unsigned long lastStepMs = 0;
	unsigned long now = millis();
	if ((now - lastStepMs) < STEP_MS)
	{
		return;
	}
	lastStepMs = now;

	// read measured current (mA)
	lastMeasuredCurrent_mA = readCurrentMilliAmps(currentSense, CURRENT_SENSE_CFG);

	// control output
	if (currentMode)
	{
		const float pidOutput = pid.step(targetCurrent, lastMeasuredCurrent_mA, now, STEP_MS);
		outputVoltage += pidOutput;
		outputVoltage = clampFloat(outputVoltage, OUTPUT_VOLTAGE_MIN, OUTPUT_VOLTAGE_MAX);

		updateCurrentLimitForTarget(psu, PSU_CFG, targetCurrent);
		setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
	}
	else
	{
		setPsuCurrentLimitIfNeeded(psu, PSU_CFG, MAX_CURRENT);
		setPsuVoltageIfNeeded(psu, PSU_CFG, outputVoltage);
	}

	// Stream output
	Serial_Pi.print(lastMeasuredCurrent_mA, 4);
	Serial_Pi.print(",");
	Serial_Pi.print(outputVoltage, 3);
	Serial_Pi.print(",");
	if (isnan(psu.voltageReadbackV))
	{
		Serial_Pi.print(outputVoltage, 3);
	}
	else
	{
		Serial_Pi.print(psu.voltageReadbackV, 3);
	}
	Serial_Pi.println();
}