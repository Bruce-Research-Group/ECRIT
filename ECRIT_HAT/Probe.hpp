#pragma once

#include <Arduino.h>
#include <math.h>

// Contact probing: find the mechanical zero between the anode (CN1) and the
// cathode (CN2) by driving a small voltage and watching for current to appear.
//
// The probe current does not flow through CN1 -- that terminal is a
// high-impedance sense tap. It flows the same way plating current does:
//
//   PSU+ -> anode -> [contact] -> cathode -> CN2 -> shunt -> CN3 -> PSU-
//
// so the INA228 is the detector. With a dry cell the gap is air, meaning
// genuinely zero current, and contact takes it to the supply's current limit.
// Against a +-0.1 mA noise floor that is a 100:1 step, which is why this keys
// on current rather than on the counter-electrode voltage collapsing.
//
// The firmware owns the detection and the shutdown. The motion controller only
// has to step and poll: every reply is one `PROBE state=...` line, and the
// state latches, so a host that misses the unsolicited line still sees the
// contact on its next query.

enum ProbeStatus : uint8_t
{
	PROBE_IDLE = 0,
	PROBE_ARMED,
	PROBE_CONTACT,
	PROBE_TIMEOUT,
	PROBE_ABORTED
};

struct ProbeConfig
{
	// Open-circuit probe voltage. Keep this low. The supply's output
	// capacitance dumps into the contact the instant metal meets metal, and
	// that energy goes as V^2 -- roughly 0.2 mJ at 1 V but 6 mJ at 5 V for a
	// few hundred microfarads. Firmware cannot help here: the discharge is over
	// in microseconds, long before any sample. The only lever is the voltage,
	// and the cathode surface you are about to plate is what pays for it.
	float volts = 1.0f;

	// Supply current limit while probing. Bounds the steady-state current after
	// the initial discharge.
	float currentLimit_mA = 10.0f;

	// Contact declared when |current| reaches this. Ten times the measured
	// noise floor, and a tenth of the current limit, so neither end is close.
	float threshold_mA = 1.0f;

	// Consecutive samples over threshold before contact is declared. Approach
	// contact can chatter; each sample is one control step.
	uint8_t debounceSamples = 2;

	// Give up and switch off after this long armed with no contact.
	unsigned long timeoutMs = 60000;
};

struct ProbeState
{
	ProbeStatus status = PROBE_IDLE;
	unsigned long startedMs = 0;
	unsigned long endedMs = 0;
	uint8_t consecutive = 0;

	// Captured at the moment contact was declared.
	float contactCurrent_mA = NAN;
	float contactCe_V = NAN;
};

inline const char *probeStatusName(ProbeStatus status)
{
	switch (status)
	{
		case PROBE_ARMED:   return "armed";
		case PROBE_CONTACT: return "contact";
		case PROBE_TIMEOUT: return "timeout";
		case PROBE_ABORTED: return "aborted";
		default:            return "idle";
	}
}

// True while the supply is energised for probing, which the output LED and the
// command guards both need to know about.
inline bool probeIsArmed(const ProbeState &state)
{
	return state.status == PROBE_ARMED;
}

// Returns true when this sample completes the debounce and contact should be
// declared. Advances the debounce counter as a side effect.
inline bool probeSampleIsContact(ProbeState &state, const ProbeConfig &cfg, float current_mA)
{
	if (isnan(current_mA) || fabsf(current_mA) < cfg.threshold_mA)
	{
		state.consecutive = 0;
		return false;
	}

	if (state.consecutive < 255)
	{
		state.consecutive++;
	}

	const uint8_t needed = (cfg.debounceSamples == 0) ? 1 : cfg.debounceSamples;
	return state.consecutive >= needed;
}
