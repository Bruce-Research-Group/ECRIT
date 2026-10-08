#pragma once

#include <Arduino.h>
#include <math.h>
#include <stdlib.h>
#include "KD3000/KD3000.hpp"

// Deadbanded setpoint writes plus periodic readback, carried over from
// Serial_PSU. The readback in the control loop does not block: see
// servicePsuReadback(). The difference on the shield is that every readback reports
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

// Which readback query is out, for servicePsuReadback().
enum PsuReadbackStage : uint8_t
{
	PSU_READBACK_IDLE = 0,
	PSU_READBACK_VOUT,
	PSU_READBACK_IOUT,
	PSU_READBACK_STATUS,
};

struct PsuState
{
	float voltageReadbackV = NAN;
	float currentReadbackA = NAN;
	unsigned long lastReadbackMs = 0;
	uint8_t readbackCount = 0;

	float lastVoltageSentV = NAN;
	float lastCurrentLimitSentA = NAN;

	// Non-blocking readback in progress. VOUT? is held here until IOUT? has
	// answered too, so the pair is only published together.
	PsuReadbackStage readbackStage = PSU_READBACK_IDLE;
	float pendingVoltageV = NAN;

	// Link health. lastGoodCommsMs is only meaningful once commsEverOk is set.
	bool commsOk = false;
	bool commsEverOk = false;
	unsigned long lastGoodCommsMs = 0;
	uint8_t consecutiveFailures = 0;

	// STATUS? decoded, refreshed at cfg.statusEvery x readbackMs.
	bool statusValid = false;
	bool cvMode = true;
	bool outputOn = false;
	// Last STATUS? byte exactly as the supply sent it, for `s`. Bits 1-5 and 7
	// are undocumented for this model, so keeping the raw value is the only way
	// to tell a genuine reading from a decode that has gone wrong again.
	uint8_t statusRaw = 0;
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
	// Straight through to the raw-byte reader. This used to call query() and
	// atol(), which turned every non-numeric status byte into 0 -- see the
	// comment on queryStatusByte() in KD3000.cpp.
	return queryStatusByte(out);
}

// Is a readback query waiting for its reply? A setpoint write now would cancel
// it (set() clears the input buffer), so the deadbanded writes below wait: the
// cache is left alone, and the next call sends the value instead.
inline bool psuReadbackBusy(const PsuState &state)
{
	return state.readbackStage != PSU_READBACK_IDLE && queryInFlight();
}

// Drop a readback in flight without counting it as a comms failure. For
// commands that must reach the supply at once.
inline void psuCancelReadback(PsuState &state)
{
	cancelQuery();
	state.readbackStage = PSU_READBACK_IDLE;
}

inline void setPsuVoltageIfNeeded(PsuState &state, const PsuConfig &cfg, float voltageV)
{
	if (psuReadbackBusy(state)) return;
	const float clamped = clampFloat(voltageV, cfg.voltageMin, cfg.voltageMax);
	if (isnan(state.lastVoltageSentV) || fabsf(clamped - state.lastVoltageSentV) >= 0.01f)
	{
		setVoltage(clamped);
		state.lastVoltageSentV = clamped;
	}
}

inline void setPsuCurrentLimitIfNeeded(PsuState &state, const PsuConfig &cfg, float currentA)
{
	if (psuReadbackBusy(state)) return;
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

// A query that gets no answer costs 350 ms instead of a few tens, so a dead
// link would otherwise spend most of its time in readback. Back off up to 4x
// while it stays dead; the comms interlock is what actually reacts to the loss.
inline unsigned long psuReadbackInterval(const PsuState &state, const PsuConfig &cfg)
{
	if (state.consecutiveFailures == 0) return cfg.readbackMs;
	const uint8_t shift = (state.consecutiveFailures > 2) ? 2 : state.consecutiveFailures;
	return cfg.readbackMs << shift;
}

inline void psuRecordReadback(PsuState &state, bool ok, float v, float i)
{
	state.commsOk = ok;
	if (ok)
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
}

inline void psuRecordStatus(PsuState &state, bool ok, uint8_t raw)
{
	state.statusValid = ok;
	if (!ok) return;
	const KD3000Status status = {raw};
	state.cvMode = status.cvMode();
	state.outputOn = status.outputOn();
	state.statusRaw = raw;
	state.lastGoodCommsMs = millis();
}

// STATUS? is skipped entirely while the link is already failing.
inline bool psuStatusDue(const PsuState &state, const PsuConfig &cfg)
{
	return state.commsOk && cfg.statusEvery > 0 && (state.readbackCount % cfg.statusEvery) == 0;
}

// Blocking readback. For `psu`, which prints the reply at once, and for `c`
// and `v`, so the comms interlock sees a fresh reply on the first control
// step. Neither runs inside the control loop.
inline void readPsuNow(PsuState &state, const PsuConfig &cfg)
{
	psuCancelReadback(state);
	state.lastReadbackMs = millis();
	state.readbackCount++;

	float v = NAN;
	float i = NAN;
	const bool vOk = psuQueryFloat("VOUT" CH "?", v);
	const bool iOk = psuQueryFloat("IOUT" CH "?", i);
	psuRecordReadback(state, vOk && iOk, v, i);

	if (psuStatusDue(state, cfg))
	{
		uint8_t raw = 0;
		const bool ok = psuQueryStatus(raw);
		psuRecordStatus(state, ok, raw);
	}
}

// The control loop's readback: VOUT?, then IOUT?, then every statusEvery-th
// time STATUS?, one query in flight at a time. Call it on every pass of the
// loop; it returns at once. `force` starts a cycle now if none is running.
//
// This used to block for the whole sequence, 150-300 ms every 500 ms, and the
// loop stopped with it: no current readings, no ADS conversions, no telemetry.
inline void servicePsuReadback(PsuState &state, const PsuConfig &cfg, unsigned long nowMs, bool force)
{
	if (state.readbackStage == PSU_READBACK_IDLE)
	{
		if (!force && (nowMs - state.lastReadbackMs) < psuReadbackInterval(state, cfg))
		{
			return;
		}
		state.lastReadbackMs = nowMs;
		state.readbackCount++;
		beginQuery("VOUT" CH "?", false);
		state.readbackStage = PSU_READBACK_VOUT;
		return;
	}

	char response[32];
	const KD3000PollResult result = pollQuery(response, sizeof(response));
	if (result == KD3000_POLL_PENDING)
	{
		return;
	}

	const PsuReadbackStage stage = state.readbackStage;
	state.readbackStage = PSU_READBACK_IDLE;

	if (result == KD3000_POLL_CANCELLED)
	{
		// Another command went out first. Not the link's fault.
		return;
	}

	if (result == KD3000_POLL_TIMEOUT)
	{
		if (stage == PSU_READBACK_STATUS) psuRecordStatus(state, false, 0);
		else psuRecordReadback(state, false, NAN, NAN);
		return;
	}

	switch (stage)
	{
		case PSU_READBACK_VOUT:
			state.pendingVoltageV = (float)atof(response);
			beginQuery("IOUT" CH "?", false);
			state.readbackStage = PSU_READBACK_IOUT;
			break;

		case PSU_READBACK_IOUT:
			psuRecordReadback(state, true, state.pendingVoltageV, (float)atof(response));
			if (psuStatusDue(state, cfg))
			{
				beginQuery("STATUS?", true);
				state.readbackStage = PSU_READBACK_STATUS;
			}
			break;

		case PSU_READBACK_STATUS:
			psuRecordStatus(state, true, (uint8_t)response[0]);
			break;

		default:
			break;
	}
}
