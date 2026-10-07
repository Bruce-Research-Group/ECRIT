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
	TRIP_COMMS,
	TRIP_SENSOR_LOST
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

// Age of a timestamp in milliseconds, as a signed value.
//
// The interlocks run against a `now` captured at the top of the control step,
// but the sensors are read a fraction of a millisecond later, so a stamp can
// legitimately sit slightly in the future. Plain unsigned subtraction wraps
// that into ~4.29e9 ms, which makes a freshly taken reading look ancient: the
// freshness tests below then skip silently, and a staleness test would fire
// on every step. Going through a signed difference makes a future stamp read
// as a small negative age, which is what it actually is.
inline long msSince(unsigned long now, unsigned long stamp)
{
	return (long)(now - stamp);
}

inline const char *tripReasonName(TripReason reason)
{
	switch (reason)
	{
		case TRIP_OVERCURRENT:    return "overcurrent";
		case TRIP_INA_ALERT:      return "ina-alert";
		case TRIP_CELL_WINDOW:    return "cell-window";
		case TRIP_OPEN_CELL:      return "open-cell";
		case TRIP_COMMS:          return "comms-loss";
		case TRIP_SENSOR_LOST:    return "sensor-lost";
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

	// --- current sense lost ---
	// Every current-based protection below depends on the INA228, and so does
	// galvanostatic control itself. If it stops answering mid-run those checks
	// quietly stop protecting anything, so losing it has to be a trip in its
	// own right rather than a silent skip. Gated on inaEverOk so a board that
	// never had an INA228 fitted can still run in voltage mode.
	// isnan() alone is deliberately not a trip: a single glitched probe
	// publishes NAN, the control loop holds its setpoint for that step, and the
	// run continues. readInaFast() clears inaOk once the failures persist.
	if (sensors.inaEverOk &&
	    (!sensors.inaOk ||
	     msSince(nowMs, sensors.inaFastUpdatedMs) > (long)cfg.staleMs))
	{
		state.offendingValue = (float)msSince(nowMs, sensors.inaFastUpdatedMs);
		return TRIP_SENSOR_LOST;
	}

	// --- over-current, firmware side ---
	if (sensors.inaOk && !isnan(sensors.current_mA) &&
	    msSince(nowMs, sensors.inaFastUpdatedMs) <= (long)cfg.staleMs &&
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
	    msSince(nowMs, sensors.adsUpdatedMs[SLOT_CELL]) <= (long)cfg.staleMs &&
	    (sensors.cell_V < cfg.cellWindowLo_V || sensors.cell_V > cfg.cellWindowHi_V))
	{
		state.offendingValue = sensors.cell_V;
		return TRIP_CELL_WINDOW;
	}

	// --- comms loss ---
	if (psu.commsEverOk &&
	    msSince(nowMs, psu.lastGoodCommsMs) > (long)cfg.commsTimeoutMs)
	{
		state.offendingValue = (float)msSince(nowMs, psu.lastGoodCommsMs);
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
