#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include <Adafruit_ADS1X15.h>
#include <Adafruit_INA228.h>

#include "Calibration.hpp"
#include "Config.hpp"

// The measurement front end: one ADS1115 and one INA228 on A4/A5.
//
// The INA228 is the primary current channel and is read synchronously (a
// register read, no conversion wait). The ADS1115 blocks for a full conversion
// per channel, so the live loop drives it through a non-blocking scanner --
// one channel in flight at a time. Calibration uses blocking averaged reads
// instead, and parks the scanner first so the two paths never fight over the
// config register.

// INA228 registers the Adafruit library does not expose.
static constexpr uint8_t INA228_REG_SOVL = 0x0C;

enum AdsSlot : uint8_t
{
	SLOT_CE = 0, // AIN0
	SLOT_RAIL,   // AIN1
	SLOT_RE,     // AIN2
	SLOT_WE,     // AIN3
	SLOT_CELL,   // AIN2 - AIN3
	SLOT_COUNT
};

struct SensorState
{
	bool adsOk = false;
	bool inaOk = false;

	// ADS1115 channels, calibration applied, in electrode units.
	float ce_V = NAN;
	float re_V = NAN;
	float cell_V = NAN; // RE - WE
	float we_A = NAN;   // coarse current from the shunt tap
	float rail_V = NAN;
	unsigned long adsUpdatedMs[SLOT_COUNT] = {0};

	// INA228, calibration applied where a calibration exists.
	float current_mA = NAN;
	float bus_V = NAN;
	float shunt_mV = NAN;
	float power_mW = NAN;
	float charge_C = NAN;
	float energy_J = NAN;
	float dieTemp_C = NAN;
	unsigned long inaFastUpdatedMs = 0;
	unsigned long inaSlowUpdatedMs = 0;

	// Latched INA228 alert (D5 or the DIAG_ALRT flags).
	bool inaAlert = false;

	// Live zero, captured by the console `z` command and held in RAM only.
	//
	// The INA228 has no analog zero to null, but it does have an input offset
	// voltage, and the reading at zero current wanders by around 0.1 mA over
	// tens of minutes -- thermoelectric EMF across the shunt terminals as the
	// board warms. That drift is the same order as the offset itself, so a
	// value baked into flash would be stale by the time it mattered. Capturing
	// it just before a run, at working temperature, is worth far more.
	float zeroCurrent_mA = 0.0f;
	float zeroWe_A = 0.0f;
};

inline Adafruit_ADS1115 ads;
inline Adafruit_INA228 ina;

// ---------------------------------------------------------------- ADS helpers

struct AdsSlotSpec
{
	uint16_t mux;
	adsGain_t gain;
	float scale; // multiply volts-at-the-pin by this to get electrode units
};

// GAIN_ONE on CE, RAIL and RE: the buffers run from AVDD ~ 5 V, so a wider PGA
// buys nothing. AIN3 sits at the shunt tap, at most 40 mV, so it gets
// GAIN_SIXTEEN. The differential pair expects well under 2 V, so GAIN_TWO.
inline AdsSlotSpec adsSlotSpec(uint8_t slot)
{
	using namespace EcritHatConfig;
	switch (slot)
	{
		case SLOT_CE:   return {MUX_BY_CHANNEL[0], GAIN_ONE, CE_DIV};
		case SLOT_RAIL: return {MUX_BY_CHANNEL[1], GAIN_ONE, RAIL_DIV};
		case SLOT_RE:   return {MUX_BY_CHANNEL[2], GAIN_ONE, 1.0f};
		case SLOT_WE:   return {MUX_BY_CHANNEL[3], GAIN_SIXTEEN, 1.0f / R_SHUNT};
		default:        return {ADS1X15_REG_CONFIG_MUX_DIFF_2_3, GAIN_TWO, 1.0f};
	}
}

inline uint8_t adsSlotToCalChannel(uint8_t slot)
{
	switch (slot)
	{
		case SLOT_CE:   return CAL_CE;
		case SLOT_RAIL: return CAL_RAIL;
		case SLOT_RE:   return CAL_RE;
		case SLOT_WE:   return CAL_WE;
		default:        return CAL_CELL;
	}
}

inline void storeAdsSlot(SensorState &state, uint8_t slot, float value)
{
	switch (slot)
	{
		case SLOT_CE:   state.ce_V = value; break;
		case SLOT_RAIL: state.rail_V = value; break;
		case SLOT_RE:   state.re_V = value; break;
		case SLOT_WE:   state.we_A = value; break;
		default:        state.cell_V = value; break;
	}
	state.adsUpdatedMs[slot] = millis();
}

// Non-blocking round robin over the five ADS slots.
class AdsScanner
{
public:
	void reset()
	{
		inFlight_ = false;
		slot_ = 0;
	}

	uint8_t slot() const { return slot_; }

	void service(SensorState &state, const BoardCal &cal)
	{
		if (!state.adsOk)
		{
			return;
		}

		const AdsSlotSpec spec = adsSlotSpec(slot_);

		if (!inFlight_)
		{
			ads.setGain(spec.gain);
			ads.startADCReading(spec.mux, false);
			startedMs_ = millis();
			inFlight_ = true;
			return;
		}

		const unsigned long elapsed = millis() - startedMs_;
		if (elapsed < EcritHatConfig::ADS_CONVERSION_MS)
		{
			return;
		}

		if (ads.conversionComplete())
		{
			// computeVolts() uses the gain currently held by the driver, so it
			// has to run before the next slot changes it.
			const float volts = ads.computeVolts(ads.getLastConversionResults());
			const uint8_t channel = adsSlotToCalChannel(slot_);
			float value = applyCal(cal.ch[channel], volts * spec.scale);
			if (slot_ == SLOT_WE)
			{
				value -= state.zeroWe_A;
			}
			storeAdsSlot(state, slot_, value);
			advance();
		}
		else if (elapsed > EcritHatConfig::ADS_TIMEOUT_MS)
		{
			// Leave the stale value in place; the freshness stamp is what the
			// interlocks look at.
			advance();
		}
	}

private:
	void advance()
	{
		inFlight_ = false;
		slot_ = (uint8_t)((slot_ + 1) % SLOT_COUNT);
	}

	uint8_t slot_ = 0;
	bool inFlight_ = false;
	unsigned long startedMs_ = 0;
};

// ------------------------------------------------------------ blocking reads

// Averaged, uncorrected read of one calibration channel, in that channel's
// units. This is the `y` in the two-point fit.
inline float readRawCalChannel(const SensorState &state, uint8_t channel, uint8_t samples)
{
	if (samples == 0) samples = 1;

	double sum = 0.0;
	for (uint8_t i = 0; i < samples; i++)
	{
		float value = NAN;
		switch (channel)
		{
			case CAL_CE:
			case CAL_RE:
			case CAL_WE:
			case CAL_RAIL:
			case CAL_CELL:
			{
				if (!state.adsOk) return NAN;
				// slot order is CE, RAIL, RE, WE, CELL; the first four map
				// straight onto AIN0..AIN3.
				const uint8_t slot = (channel == CAL_CE)   ? SLOT_CE
				                   : (channel == CAL_RAIL) ? SLOT_RAIL
				                   : (channel == CAL_RE)   ? SLOT_RE
				                   : (channel == CAL_WE)   ? SLOT_WE
				                                           : SLOT_CELL;
				const AdsSlotSpec spec = adsSlotSpec(slot);
				ads.setGain(spec.gain);
				const int16_t counts = (slot == SLOT_CELL)
					? ads.readADC_Differential_2_3()
					: ads.readADC_SingleEnded(slot);
				value = ads.computeVolts(counts) * spec.scale;
				break;
			}
			case CAL_INA_I:
				if (!state.inaOk) return NAN;
				value = ina.readCurrent();
				break;
			case CAL_INA_V:
				if (!state.inaOk) return NAN;
				value = ina.readBusVoltage();
				break;
			default:
				return NAN;
		}

		if (isnan(value)) return NAN;
		sum += value;
	}

	return (float)(sum / samples);
}

// ------------------------------------------------------------- INA228 set-up

// The Adafruit library declares AlertLimit but never allocates it (version
// 3.0.0), so writing through it would dereference a null pointer. Write the
// shunt overvoltage threshold register directly instead. With ADCRANGE = 1 the
// SOVL LSB is 1.25 uV, so 5.12 A maps to 32767 counts -- full scale.
inline bool inaSetOvercurrentLimit(float amps)
{
	const float shuntVolts = fabsf(amps) * EcritHatConfig::R_SHUNT;
	long counts = lroundf(shuntVolts / 1.25e-6f);
	if (counts > 32767) counts = 32767;
	if (counts < 0) counts = 0;

	Wire.beginTransmission(EcritHatConfig::ADDR_INA228);
	Wire.write(INA228_REG_SOVL);
	Wire.write((uint8_t)((counts >> 8) & 0xFF));
	Wire.write((uint8_t)(counts & 0xFF));
	return Wire.endTransmission() == 0;
}

// ADC range, shunt calibration, averaging and the over-current alert wiring.
inline void configureIna(float overCurrentTripA)
{
	ina.setADCRange(1);                                  // +-40.96 mV shunt FS
	ina.setShunt(EcritHatConfig::R_SHUNT,
	             EcritHatConfig::INA_FULL_SCALE_A);      // 9.766 uA current LSB
	ina.setAveragingCount(INA228_COUNT_16);
	ina.setCurrentConversionTime(INA228_TIME_1052_us);
	ina.setVoltageConversionTime(INA228_TIME_1052_us);

	// begin() leaves the conversion-ready alert on, which would pulse D5 ~20
	// times a second. setAlertType() only covers DIAG_ALRT bits 8..13, so the
	// CNVR bit at 14 has to be cleared separately.
	Adafruit_I2CRegisterBits conversionReadyAlert(ina.Diag_Alert, 1, 14);
	conversionReadyAlert.write(0);

	ina.setAlertType(INA228_ALERT_OVERCURRENT);
	ina.setAlertLatch(INA228_ALERT_LATCH_ENABLED);
	inaSetOvercurrentLimit(overCurrentTripA);
}

// ---------------------------------------------------------------- INA reads

inline void readInaFast(SensorState &state, const BoardCal &cal)
{
	if (!state.inaOk) return;
	state.current_mA = applyCal(cal.ch[CAL_INA_I], ina.readCurrent()) - state.zeroCurrent_mA;
	state.inaFastUpdatedMs = millis();
}

// Capture the present zero for the current channels. The caller must have the
// output off and nothing driving the shunt, and must park the ADS scanner
// first -- readRawCalChannel() drives the converter directly.
inline void captureZero(SensorState &state, const BoardCal &cal, uint8_t samples)
{
	if (state.inaOk)
	{
		const float raw = readRawCalChannel(state, CAL_INA_I, samples);
		if (!isnan(raw)) state.zeroCurrent_mA = applyCal(cal.ch[CAL_INA_I], raw);
	}
	if (state.adsOk)
	{
		const float raw = readRawCalChannel(state, CAL_WE, samples);
		if (!isnan(raw)) state.zeroWe_A = applyCal(cal.ch[CAL_WE], raw);
	}
}

inline void clearZero(SensorState &state)
{
	state.zeroCurrent_mA = 0.0f;
	state.zeroWe_A = 0.0f;
}

inline void readInaSlow(SensorState &state, const BoardCal &cal)
{
	if (!state.inaOk) return;
	state.bus_V = applyCal(cal.ch[CAL_INA_V], ina.readBusVoltage());
	state.shunt_mV = ina.readShuntVoltage();
	state.power_mW = ina.readPower();
	state.charge_C = ina.readCharge();
	state.energy_J = ina.readEnergy();
	state.dieTemp_C = ina.readDieTemp();
	state.inaSlowUpdatedMs = millis();
}

// Reconstructed WE - CE. There is no hardware differential between those two
// nodes, and they are sampled sequentially, so this is only as good as the
// settling of the slower one.
inline float reconstructWeMinusCe(const SensorState &state)
{
	if (isnan(state.ce_V) || isnan(state.re_V)) return NAN;
	// WE sits at the shunt drop above ground; RE - cell gives it back.
	const float we_V = isnan(state.cell_V) ? NAN : (state.re_V - state.cell_V);
	if (isnan(we_V)) return NAN;
	return we_V - state.ce_V;
}
