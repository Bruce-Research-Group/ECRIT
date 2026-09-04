#pragma once

#include <Arduino.h>
#include <EEPROM.h>
#include <math.h>
#include <stddef.h>
#include <string.h>
#include <strings.h>

// Per-board two-point linear correction.
//
//   g = (x2 - x1) / (y2 - y1),  o = x1 - g*y1,  x_corrected = g*y + o
//
// where y is the value the firmware computes from raw counts and x is what a
// reference instrument says. Every channel defaults to unity gain / zero
// offset, so an uncalibrated board still reads in the right units.
//
// Storage is the RA4M1 data flash behind the core's EEPROM library. The record
// carries a 0xEC17 magic plus a layout version and a
// CRC32, so a half-finished write or a struct layout change falls back to
// defaults instead of loading garbage into the control loop.

enum CalChannel : uint8_t
{
	CAL_CE = 0,   // AIN0, volts at CN1, after the x7.6667 divider scaling
	CAL_RE,       // AIN2, volts at CN4
	CAL_CELL,     // AIN2 - AIN3 differential, volts
	CAL_WE,       // AIN3 over the shunt, amps (diagnostic cross-check)
	CAL_RAIL,     // AIN1 x2, volts on the 5 V rail
	CAL_INA_I,    // INA228 CURRENT, milliamps (primary loop input)
	CAL_INA_V,    // INA228 VBUS, volts at CE
	CAL_COUNT
};

struct ChannelCal
{
	float gain = 1.0f;
	float offset = 0.0f;
};

// Control gains live in the same record as the channel corrections. They are
// as much a property of a particular cell and supply as the channel fits are
// of a particular board, and nobody wants to retype them after a reflash.
//
// Defaults are the incremental-form values: kp is the only active term, and
// enabling ki adds a second integrator that will oscillate.
struct PidGains
{
	float kp = 0.01f;
	float ki = 0.0f;
	float kd = 0.0f;
};

static constexpr uint16_t CAL_MAGIC = 0xEC17;
// Version 2 added PidGains. A version 1 record fails the check and falls back
// to defaults rather than being read at the wrong offsets.
static constexpr uint16_t CAL_VERSION = 2;
static constexpr int CAL_EEPROM_ADDR = 0;

struct BoardCal
{
	uint16_t magic = CAL_MAGIC;
	uint16_t version = CAL_VERSION;
	ChannelCal ch[CAL_COUNT];
	PidGains pid;
	uint32_t crc = 0;
};

// Two-point working set. Lives in RAM only: the points are scaffolding for the
// fit, the fit result is what gets persisted.
struct CalPoints
{
	float xLow = 0.0f, yLow = 0.0f;
	float xHigh = 0.0f, yHigh = 0.0f;
	bool hasLow = false, hasHigh = false;
};

inline float applyCal(const ChannelCal &c, float raw)
{
	return c.gain * raw + c.offset;
}

inline const char *calChannelName(uint8_t channel)
{
	switch (channel)
	{
		case CAL_CE:    return "ce";
		case CAL_RE:    return "re";
		case CAL_CELL:  return "cell";
		case CAL_WE:    return "we";
		case CAL_RAIL:  return "rail";
		case CAL_INA_I: return "inai";
		case CAL_INA_V: return "inav";
		default:        return "?";
	}
}

inline const char *calChannelUnit(uint8_t channel)
{
	switch (channel)
	{
		case CAL_WE:    return "A";
		case CAL_INA_I: return "mA";
		default:        return "V";
	}
}

// Returns CAL_COUNT when the name does not match a channel.
inline uint8_t calChannelByName(const char *name)
{
	if (name == nullptr) return CAL_COUNT;
	for (uint8_t i = 0; i < CAL_COUNT; i++)
	{
		if (strcasecmp(name, calChannelName(i)) == 0)
		{
			return i;
		}
	}
	return CAL_COUNT;
}

inline uint32_t calCrc32(const uint8_t *data, size_t length)
{
	uint32_t crc = 0xFFFFFFFFul;
	for (size_t i = 0; i < length; i++)
	{
		crc ^= data[i];
		for (uint8_t bit = 0; bit < 8; bit++)
		{
			crc = (crc & 1u) ? ((crc >> 1) ^ 0xEDB88320ul) : (crc >> 1);
		}
	}
	return ~crc;
}

// CRC covers everything ahead of the crc field itself.
inline uint32_t calRecordCrc(const BoardCal &record)
{
	return calCrc32(reinterpret_cast<const uint8_t *>(&record),
	                offsetof(BoardCal, crc));
}

inline void calSetDefaults(BoardCal &record)
{
	record = BoardCal();
	record.crc = calRecordCrc(record);
}

inline bool calSave(BoardCal &record)
{
	record.magic = CAL_MAGIC;
	record.version = CAL_VERSION;
	record.crc = calRecordCrc(record);
	EEPROM.put(CAL_EEPROM_ADDR, record);

	// Read back: data flash writes can fail silently on a worn or busy block.
	BoardCal check;
	EEPROM.get(CAL_EEPROM_ADDR, check);
	return check.magic == CAL_MAGIC &&
	       check.version == CAL_VERSION &&
	       check.crc == calRecordCrc(check);
}

// Returns true when a valid stored record was loaded, false when the caller
// got defaults instead.
inline bool calLoad(BoardCal &record)
{
	BoardCal stored;
	EEPROM.get(CAL_EEPROM_ADDR, stored);

	if (stored.magic != CAL_MAGIC ||
	    stored.version != CAL_VERSION ||
	    stored.crc != calRecordCrc(stored))
	{
		calSetDefaults(record);
		return false;
	}

	// A NaN or absurd gain that survived the CRC would still wreck the loop.
	for (uint8_t i = 0; i < CAL_COUNT; i++)
	{
		if (isnan(stored.ch[i].gain) || isnan(stored.ch[i].offset) ||
		    stored.ch[i].gain == 0.0f || fabsf(stored.ch[i].gain) > 1000.0f)
		{
			calSetDefaults(record);
			return false;
		}
	}

	// Zero is a legitimate gain here -- ki and kd ship at zero -- so only NaN
	// and implausible magnitudes are rejected.
	if (isnan(stored.pid.kp) || isnan(stored.pid.ki) || isnan(stored.pid.kd) ||
	    fabsf(stored.pid.kp) > 1000.0f || fabsf(stored.pid.ki) > 1000.0f ||
	    fabsf(stored.pid.kd) > 1000.0f)
	{
		calSetDefaults(record);
		return false;
	}

	record = stored;
	return true;
}

inline bool calErase(BoardCal &record)
{
	BoardCal blank;
	blank.magic = 0;
	blank.version = 0;
	blank.crc = 0;
	EEPROM.put(CAL_EEPROM_ADDR, blank);
	calSetDefaults(record);

	BoardCal check;
	EEPROM.get(CAL_EEPROM_ADDR, check);
	return check.magic != CAL_MAGIC;
}

// Two-point fit. Fails when the two y values are too close to separate, which
// is what you get if the operator forgets to change the applied stimulus.
inline bool calFit(const CalPoints &points, ChannelCal &out)
{
	if (!points.hasLow || !points.hasHigh)
	{
		return false;
	}

	const float dy = points.yHigh - points.yLow;
	if (fabsf(dy) < 1e-9f)
	{
		return false;
	}

	const float gain = (points.xHigh - points.xLow) / dy;
	if (isnan(gain) || gain == 0.0f || fabsf(gain) > 1000.0f)
	{
		return false;
	}

	out.gain = gain;
	out.offset = points.xLow - gain * points.yLow;
	return true;
}
