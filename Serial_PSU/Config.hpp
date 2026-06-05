#pragma once

#include <Arduino.h>

#include "CurrentSense.hpp"
#include "PsuControl.hpp"

namespace SerialPsuConfig
{
	// Pins
	static constexpr uint8_t CURRENT_PIN = A3;

	// Timing
	static constexpr unsigned long STEP_MS = 50;
	static constexpr unsigned long PSU_READBACK_MS = 500; // ~2 Hz

	// Output limits
	static constexpr float OUTPUT_VOLTAGE_MIN = 0.0f;
	static constexpr float OUTPUT_VOLTAGE_MAX = 30.0f;

	// Current limit behavior
	static constexpr float CURRENT_LIMIT_MULTIPLIER = 1.5f;
	static constexpr float CURRENT_LIMIT_MIN_A = 0.01f;

	// Current sense constants
	static constexpr float VREF = 4.782f;           // (V) measured actual 5V supply voltage
	static constexpr float RSHUNT = 0.51f;          // (Ohm) Shunt resistor value
	static constexpr float Rf = 98000.0f;           // (Ohm) Rf Gain resistor value
	static constexpr float Rg = 19210.0f;           // (Ohm) Rg Gain resistor value

	static constexpr float GAIN = 1.0f + (Rf / Rg); // INA gain calculation
	static constexpr float MAX_CURRENT = (VREF / (GAIN * RSHUNT)); // (mA) Theoretical max current

	// Current calibration factors
	// the actual current is consistently lower than the current we read from the ADC
	static constexpr float CURRENT_CALIBRATION_FACTOR = 0.955f; // Adjust this factor based on calibration measurements

	// Current sense config
	static constexpr int ZERO_SAMPLES = 512;        // Number of samples to average for zero calibration
	static constexpr int MEASURE_SAMPLES = 64;      // Number of samples to average for current measurement

	// ADC full-scale for 14-bit read resolution.
	static constexpr int ADC_RESOLUTION_BITS = 14;
	static constexpr float ADC_FULL_SCALE = (float)((1 << ADC_RESOLUTION_BITS) - 1);

	inline const CurrentSenseConfig CURRENT_SENSE_CFG = {
		CURRENT_PIN,
		VREF,
		RSHUNT,
		GAIN,
		ADC_FULL_SCALE,
		ZERO_SAMPLES,
		MEASURE_SAMPLES,
		CURRENT_CALIBRATION_FACTOR,
	};

	inline const PsuConfig PSU_CFG = {
		OUTPUT_VOLTAGE_MIN,
		OUTPUT_VOLTAGE_MAX,
		MAX_CURRENT,
		CURRENT_LIMIT_MIN_A,
		CURRENT_LIMIT_MULTIPLIER,
		PSU_READBACK_MS,
	};
} // namespace SerialPsuConfig
