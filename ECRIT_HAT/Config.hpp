#pragma once

#include <Arduino.h>

#include "PsuControl.hpp"

// Every tunable constant for the ECRIT-HAT firmware, in one namespace.

namespace EcritHatConfig
{
	// ---- Pin map -----------------------------------------------------------
	// D0/D1 carry the PSU UART through SJ1/SJ2 on an Uno R4, which is Serial1.
	//
	// LED1 (red, D4) sits next to CN1 and is the output indicator: solid while
	// the output is live, flashing on a latched fault. LED2 (yellow, D13) is
	// the general-purpose user LED.
	static constexpr uint8_t PIN_LED_OUTPUT = 4;  // LED1 red,    HIGH = lit
	static constexpr uint8_t PIN_LED_USER   = 13; // LED2 yellow, HIGH = lit, also SPI SCK
	static constexpr uint8_t PIN_INA_ALERT  = 5;  // INA228 ALERT, open drain, active LOW
	static constexpr uint8_t PIN_ADS_ALERT  = 6;  // ADS1115 ALERT/RDY, open drain, active LOW
	static constexpr uint8_t PIN_CTS        = 9;  // R2OUT, LOW = asserted
	static constexpr uint8_t PIN_RTS        = 10; // T2IN,  LOW = asserted

	// ---- LED timing --------------------------------------------------------
	static constexpr unsigned long LED_FAULT_FLASH_MS = 125;   // 4 Hz on a trip
	static constexpr unsigned long LED_HEARTBEAT_PERIOD_MS = 2000;
	static constexpr unsigned long LED_HEARTBEAT_ON_MS = 60;

	// ---- I2C ---------------------------------------------------------------
	static constexpr uint8_t  ADDR_ADS1115 = 0x48;
	static constexpr uint8_t  ADDR_INA228  = 0x40;
	static constexpr uint32_t I2C_CLOCK_HZ = 400000;

	// ---- Analog front end scaling ------------------------------------------
	static constexpr float CE_DIV   = 7.666667f; // (220k + 33k) / 33k
	static constexpr float RAIL_DIV = 2.0f;      // 10k / 10k
	static constexpr float R_SHUNT  = 0.008f;    // ohm
	static constexpr float INA_FULL_SCALE_A = 5.12f; // 40.96 mV / 8 mOhm

	// ADS1115 conversion time at 128 SPS is 7.8 ms. The scanner waits this
	// long before it starts asking conversionComplete(), so polling does not
	// flood the bus.
	static constexpr unsigned long ADS_CONVERSION_MS = 8;
	static constexpr unsigned long ADS_TIMEOUT_MS = 60;

	// ---- Link parameters ---------------------------------------------------
	static constexpr unsigned long CONSOLE_BAUD = 9600;
	static constexpr unsigned long PSU_BAUD = 9600;

	// ---- Loop timing -------------------------------------------------------
	static constexpr unsigned long STEP_MS = 50;           // 20 Hz control loop
	static constexpr unsigned long PSU_READBACK_MS = 500;  // ~2 Hz VOUT?/IOUT?
	static constexpr uint8_t PSU_STATUS_EVERY = 4;         // STATUS? at ~0.5 Hz
	static constexpr unsigned long INA_SLOW_MS = 500;      // VBUS, charge, temp

	// ---- Output limits -----------------------------------------------------
	static constexpr float OUTPUT_VOLTAGE_MIN = 0.0f;
	static constexpr float OUTPUT_VOLTAGE_MAX = 30.0f;
	static constexpr float MAX_CURRENT_A = 5.0f; // KD3005P ceiling
	static constexpr float CURRENT_LIMIT_MIN_A = 0.01f;
	static constexpr float CURRENT_LIMIT_MULTIPLIER = 1.5f;

	static constexpr float DEFAULT_OUTPUT_VOLTAGE = 0.5f;
	static constexpr float DEFAULT_TARGET_CURRENT_MA = 10.0f;

	// ---- PSU detection -----------------------------------------------------
	// A missing supply must not wedge the sketch: the board still has to answer
	// the console so the host can identify the port and so calibration works
	// with nothing attached.
	static constexpr uint8_t PSU_DETECT_ATTEMPTS = 3;
	static constexpr unsigned long PSU_DETECT_RETRY_MS = 3000;

	// ---- Calibration console ----------------------------------------------
	static constexpr uint8_t CAL_DEFAULT_SAMPLES = 16;
	static constexpr uint8_t CAL_MAX_SAMPLES = 64;

	// Samples averaged when the `z` command captures the live current zero.
	static constexpr uint8_t ZERO_SAMPLES = 64;

	static constexpr PsuConfig PSU_CFG = {
		OUTPUT_VOLTAGE_MIN,
		OUTPUT_VOLTAGE_MAX,
		MAX_CURRENT_A,
		CURRENT_LIMIT_MIN_A,
		CURRENT_LIMIT_MULTIPLIER,
		PSU_READBACK_MS,
		PSU_STATUS_EVERY,
	};
} // namespace EcritHatConfig
