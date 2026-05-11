#pragma once

#include <Arduino.h>
#include <math.h>
#include "KD3000/KD3000.hpp"

struct PsuConfig
{
	float voltageMin;
	float voltageMax;
	float maxCurrentA;
	float currentLimitMinA;
	float currentLimitMultiplier;
	unsigned long readbackMs;
};

struct PsuState
{
	float voltageReadbackV = NAN;
	float currentReadbackA = NAN;
	unsigned long lastReadbackMs = 0;

	float lastVoltageSentV = NAN;
	float lastCurrentLimitSentA = NAN;
};

inline float clampFloat(float value, float lo, float hi)
{
	if (value < lo) return lo;
	if (value > hi) return hi;
	return value;
}

inline void setPsuVoltageIfNeeded(PsuState &state, const PsuConfig &cfg, float voltageV)
{
	const float clamped = clampFloat(voltageV, cfg.voltageMin, cfg.voltageMax);
	if (isnan(state.lastVoltageSentV) || fabsf(clamped - state.lastVoltageSentV) >= 0.01f)
	{
		setVoltage(clamped);
		state.lastVoltageSentV = clamped;
	}
}

inline void setPsuCurrentLimitIfNeeded(PsuState &state, const PsuConfig &cfg, float currentA)
{
	const float clamped = clampFloat(currentA, cfg.currentLimitMinA, cfg.maxCurrentA);
	if (isnan(state.lastCurrentLimitSentA) || fabsf(clamped - state.lastCurrentLimitSentA) >= 0.005f)
	{
		setCurrent(clamped);
		state.lastCurrentLimitSentA = clamped;
	}
}

inline void updateCurrentLimitForTarget(PsuState &state, const PsuConfig &cfg, float targetCurrent_mA)
{
	const float targetA = targetCurrent_mA / 1000.0f;
	const float limitA = targetA * cfg.currentLimitMultiplier;
	setPsuCurrentLimitIfNeeded(state, cfg, limitA);
}

inline void updatePsuReadbackIfDue(PsuState &state, const PsuConfig &cfg, unsigned long nowMs, bool force)
{
	if (!force && (nowMs - state.lastReadbackMs) < cfg.readbackMs)
	{
		return;
	}

	state.voltageReadbackV = getVoltage();
	state.currentReadbackA = getCurrent();
	state.lastReadbackMs = nowMs;
}
