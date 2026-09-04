#pragma once

#include <Arduino.h>
#include <math.h>

#include "Config.hpp"
#include "PsuControl.hpp"
#include "Sensors.hpp"

// Safety interlocks. Serial_PSU shipped with none of them; the only protection
// there was the output voltage clamp.
//
// Defaults are deliberately loose. With no cell and no supply attached the
// board must be able to sit powered and idle without nuisance trips, so every
// threshold is set outside anything the hardware can produce on the bench.
// Tighten them for a real run with the `lim` command.

enum TripReason : uint8_t
{
	TRIP_NONE = 0,
	TRIP_OVERCURRENT,
	TRIP_INA_ALERT,
	TRIP_CELL_WINDOW,
	TRIP_OPEN_CELL,
	TRIP_COMMS
	// A startup comms failure has no trip state: setup() sends OUT0
	// unconditionally and then carries on without a supply, so there is
	// nothing to latch.
};

struct InterlockConfig
{
	bool enabled = true;

	// Over-current, checked against the INA228 reading in mA.
	float overCurrent_mA = 4000.0f;

	// Hardware over-current latch on D5 / DIAG_ALRT, in amps.
	float inaAlertLimit_A = 4.5f;
	bool useInaAlertPin = true;

	// Cell potential window on AIN2 - AIN3, volts. The default spans the whole
	// measurable range, so it never fires until somebody sets a real window
	// for their chemistry.
	float cellWindowLo_V = -1.0f;
	float cellWindowHi_V = 4.096f;

	// Open cell: the setpoint is pinned near the compliance ceiling but the
	// current never arrives.
	float compliance_V = 29.5f;
	float complianceMinCurrent_mA = 1.0f;
	unsigned long complianceHoldMs = 3000;

	// Comms loss while the loop is running.
	unsigned long commsTimeoutMs = 3000;

	// A measurement older than this is not trusted for tripping.
	unsigned long staleMs = 1500;
};

struct InterlockState
{
	TripReason reason = TRIP_NONE;
	float offendingValue = NAN;
	unsigned long complianceSinceMs = 0;
};

inline const char *tripReasonName(TripReason reason)
{
	switch (reason)
	{
		case TRIP_OVERCURRENT:    return "overcurrent";
		case TRIP_INA_ALERT:      return "ina-alert";
		case TRIP_CELL_WINDOW:    return "cell-window";
		case TRIP_OPEN_CELL:      return "open-cell";
		case TRIP_COMMS:          return "comms-loss";
		default:                  return "none";
	}
}

// Runs once per control step while the output is on. Returns the reason to
// trip, or TRIP_NONE. It does not act -- the caller owns the output.
inline TripReason checkInterlocks(InterlockState &state,
                                  const InterlockConfig &cfg,
                                  const SensorState &sensors,
                                  const PsuState &psu,
                                  bool currentMode,
                                  float commandedVoltage,
                                  unsigned long nowMs)
{
	state.offendingValue = NAN;

	if (!cfg.enabled)
	{
		state.complianceSinceMs = 0;
		return TRIP_NONE;
	}

	// --- over-current, firmware side ---
	if (sensors.inaOk && !isnan(sensors.current_mA) &&
	    (nowMs - sensors.inaFastUpdatedMs) <= cfg.staleMs &&
	    fabsf(sensors.current_mA) > cfg.overCurrent_mA)
	{
		state.offendingValue = sensors.current_mA;
		return TRIP_OVERCURRENT;
	}

	// --- over-current, hardware latch on D5 ---
	if (cfg.useInaAlertPin && sensors.inaAlert)
	{
		return TRIP_INA_ALERT;
	}

	// --- cell potential window, AIN2 - AIN3 ---
	if (sensors.adsOk && !isnan(sensors.cell_V) &&
	    (nowMs - sensors.adsUpdatedMs[SLOT_CELL]) <= cfg.staleMs &&
	    (sensors.cell_V < cfg.cellWindowLo_V || sensors.cell_V > cfg.cellWindowHi_V))
	{
		state.offendingValue = sensors.cell_V;
		return TRIP_CELL_WINDOW;
	}

	// --- comms loss ---
	if (psu.commsEverOk && (nowMs - psu.lastGoodCommsMs) > cfg.commsTimeoutMs)
	{
		state.offendingValue = (float)(nowMs - psu.lastGoodCommsMs);
		return TRIP_COMMS;
	}

	// --- open cell / compliance ---
	// Only meaningful in galvanostatic mode: in voltage mode a low current is
	// exactly what a light load looks like.
	if (currentMode && commandedVoltage >= cfg.compliance_V &&
	    sensors.inaOk && !isnan(sensors.current_mA) &&
	    fabsf(sensors.current_mA) < cfg.complianceMinCurrent_mA)
	{
		if (state.complianceSinceMs == 0)
		{
			state.complianceSinceMs = nowMs;
		}
		else if ((nowMs - state.complianceSinceMs) > cfg.complianceHoldMs)
		{
			state.offendingValue = sensors.current_mA;
			return TRIP_OPEN_CELL;
		}
	}
	else
	{
		state.complianceSinceMs = 0;
	}

	return TRIP_NONE;
}
