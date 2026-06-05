#pragma once

#include <Arduino.h>

struct CurrentSenseConfig
{
	uint8_t pin;
	float vref;
	float rshunt;
	float gain;
	float adcFullScale;
	int zeroSamples;
	int measureSamples;
	float calibrationFactor;
};

struct CurrentSenseState
{
	float zeroRaw = 0.0f;
};

inline float readAverage(uint8_t pin, int n)
{
	uint32_t sum = 0;
	for (int i = 0; i < n; i++)
	{
		sum += (uint32_t)analogRead(pin);
	}
	return (float)sum / (float)n;
}

inline void calibrateZero(CurrentSenseState &state, const CurrentSenseConfig &cfg)
{
	state.zeroRaw = readAverage(cfg.pin, cfg.zeroSamples);
}

inline float readCurrentMilliAmps(const CurrentSenseState &state, const CurrentSenseConfig &cfg)
{
	const float raw = readAverage(cfg.pin, cfg.measureSamples);
	const float vout = (raw - state.zeroRaw) * cfg.vref / cfg.adcFullScale;
	const float currentA = vout / (cfg.gain * cfg.rshunt);
	return currentA * 1000.0f * cfg.calibrationFactor; // convert to mA and apply calibration
}
