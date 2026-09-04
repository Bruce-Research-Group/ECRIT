#pragma once

#include <Arduino.h>
#include <math.h>
#include <stdlib.h>
#include "KD3000/KD3000.hpp"

// Deadbanded setpoint writes plus periodic readback, carried over from
// Serial_PSU. The difference on the shield is that every readback reports
// whether the link actually answered:
// getVoltage() returns atof("") = 0.000 on a timeout, so a dead RS-232 link
// otherwise reads as a plausible 0.000 V. The comms-loss interlock needs the
// truth, so the readback path goes through query() directly.

struct PsuConfig
{
	float voltageMin;
	float voltageMax;
	float maxCurrentA;
	float currentLimitMinA;
	float currentLimitMultiplier;
	unsigned long readbackMs;
	uint8_t statusEvery; // issue STATUS? once every N readbacks
};

struct PsuState
{
	float voltageReadbackV = NAN;
	float currentReadbackA = NAN;
	unsigned long lastReadbackMs = 0;
	uint8_t readbackCount = 0;

	float lastVoltageSentV = NAN;
	float lastCurrentLimitSentA = NAN;

	// Link health. lastGoodCommsMs is only meaningful once commsEverOk is set.
	bool commsOk = false;
	bool commsEverOk = false;
	unsigned long lastGoodCommsMs = 0;
	uint8_t consecutiveFailures = 0;

	// STATUS? decoded, refreshed at cfg.statusEvery x readbackMs.
	bool statusValid = false;
	bool cvMode = true;
	bool outputOn = false;
};

inline float clampFloat(float value, float lo, float hi)
{
	if (value < lo) return lo;
	if (value > hi) return hi;
	return value;
}

// query() with the return length checked, so a timeout is distinguishable
// from a real 0.000 reply.
inline bool psuQueryFloat(const char *command, float &out)
{
	char response[32];
	if (query(command, response, sizeof(response)) == 0)
	{
		return false;
	}
	out = (float)atof(response);
	return true;
}

inline bool psuQueryStatus(uint8_t &out)
{
	char response[32];
	if (query("STATUS?", response, sizeof(response)) == 0)
	{
		return false;
	}
	out = (uint8_t)atol(response);
	return true;
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

// Forget the deadband history so the next setpoint write is unconditional.
// Used after the output is re-enabled or the link comes back.
inline void invalidatePsuSetpointCache(PsuState &state)
{
	state.lastVoltageSentV = NAN;
	state.lastCurrentLimitSentA = NAN;
}

inline void updatePsuReadbackIfDue(PsuState &state, const PsuConfig &cfg, unsigned long nowMs, bool force)
{
	// A query that gets no answer costs 350 ms instead of 55 ms, so a dead link
	// would otherwise spend more time in readback than in the control loop.
	// Back off up to 4x while it stays dead; the comms interlock is what
	// actually reacts to the loss.
	unsigned long interval = cfg.readbackMs;
	if (state.consecutiveFailures > 0)
	{
		const uint8_t shift = (state.consecutiveFailures > 2) ? 2 : state.consecutiveFailures;
		interval = cfg.readbackMs << shift;
	}

	if (!force && (nowMs - state.lastReadbackMs) < interval)
	{
		return;
	}

	state.lastReadbackMs = nowMs;
	state.readbackCount++;

	float v = NAN;
	float i = NAN;
	const bool vOk = psuQueryFloat("VOUT" CH "?", v);
	const bool iOk = psuQueryFloat("IOUT" CH "?", i);

	state.commsOk = vOk && iOk;
	if (state.commsOk)
	{
		state.voltageReadbackV = v;
		state.currentReadbackA = i;
		state.commsEverOk = true;
		state.lastGoodCommsMs = millis();
		state.consecutiveFailures = 0;
	}
	else if (state.consecutiveFailures < 255)
	{
		state.consecutiveFailures++;
	}

	// STATUS? costs another blocking query. Skip it entirely while the link is
	// already failing.
	if (state.commsOk && cfg.statusEvery > 0 && (state.readbackCount % cfg.statusEvery) == 0)
	{
		uint8_t raw = 0;
		if (psuQueryStatus(raw))
		{
			const KD3000Status status = {raw};
			state.cvMode = status.cvMode();
			state.outputOn = status.outputOn();
			state.statusValid = true;
			state.lastGoodCommsMs = millis();
		}
		else
		{
			state.statusValid = false;
		}
	}
}
