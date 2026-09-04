#pragma once

#include <Arduino.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "Calibration.hpp"
#include "CommandParser.hpp"
#include "Config.hpp"
#include "Sensors.hpp"

// Interactive two-point calibration over the USB console.
//
// While calibration mode is on, the control loop is not running and the
// ADS scanner is parked, so every read here is a blocking averaged read of the
// raw (uncorrected) value. Nothing is written to flash until `save`.
//
// Typical session for one channel:
//
//   k                    enter calibration mode
//   lo ce 0.0            short CN1 to GND, tell it the reference reads 0 V
//   hi ce 25.000         apply 25 V, tell it what the DMM says
//   fit ce               compute gain and offset, apply in RAM
//   raw ce               sanity check
//   save                 commit to data flash
//   x                    leave

class CalConsole
{
public:
	bool active() const { return active_; }

	void enter(Stream &out, AdsScanner &scanner)
	{
		active_ = true;
		scanner.reset();
		out.println("CAL MODE");
		out.println("Control loop suspended. Type 'help' for commands or 'x' to exit.");
		printChannels(out);
	}

	void leave(Stream &out, AdsScanner &scanner)
	{
		active_ = false;
		scanner.reset();
		out.println("CAL MODE OFF");
	}

	// Returns true when the command was consumed by calibration mode.
	bool handle(const ParsedCommand &cmd, Stream &out, BoardCal &cal,
	            const SensorState &sensors, AdsScanner &scanner)
	{
		if (!active_)
		{
			return false;
		}

		if (cmd.is("x") || cmd.is("q") || cmd.is("exit"))
		{
			leave(out, scanner);
			return true;
		}

		if (cmd.is("help") || cmd.is("h") || cmd.is("?"))
		{
			printHelp(out);
			return true;
		}

		if (cmd.is("list") || cmd.is("l"))
		{
			printTable(out, cal, sensors);
			return true;
		}

		if (cmd.is("avg"))
		{
			if (cmd.has(1))
			{
				long n = (long)cmd.number(1, samples_);
				if (n < 1) n = 1;
				if (n > EcritHatConfig::CAL_MAX_SAMPLES) n = EcritHatConfig::CAL_MAX_SAMPLES;
				samples_ = (uint8_t)n;
			}
			out.print("Samples per reading = ");
			out.println(samples_);
			return true;
		}

		if (cmd.is("raw"))
		{
			const uint8_t ch = requireChannel(cmd, out);
			if (ch < CAL_COUNT)
			{
				const float raw = readRawCalChannel(sensors, ch, samples_);
				out.print("raw ");
				out.print(calChannelName(ch));
				out.print(" = ");
				printValue(out, raw);
				out.print(" ");
				out.print(calChannelUnit(ch));
				out.print("  corrected = ");
				printValue(out, applyCal(cal.ch[ch], raw));
				out.print(" ");
				out.println(calChannelUnit(ch));
			}
			return true;
		}

		if (cmd.is("lo") || cmd.is("hi"))
		{
			const bool low = cmd.is("lo");
			const uint8_t ch = requireChannel(cmd, out);
			if (ch >= CAL_COUNT)
			{
				return true;
			}
			if (!cmd.has(2))
			{
				out.println("Need the reference value. Example: lo ce 0.0");
				return true;
			}

			const float known = cmd.number(2);
			const float raw = readRawCalChannel(sensors, ch, samples_);
			if (isnan(raw))
			{
				out.println("Read failed. Device not responding.");
				return true;
			}

			if (low)
			{
				points_[ch].xLow = known;
				points_[ch].yLow = raw;
				points_[ch].hasLow = true;
			}
			else
			{
				points_[ch].xHigh = known;
				points_[ch].yHigh = raw;
				points_[ch].hasHigh = true;
			}

			out.print(low ? "Low point " : "High point ");
			out.print(calChannelName(ch));
			out.print(": reference = ");
			printValue(out, known);
			out.print("  measured = ");
			printValue(out, raw);
			out.print(" ");
			out.println(calChannelUnit(ch));
			return true;
		}

		// Single-point gain-only fit, for channels where the offset is
		// negligible and only the ratio is in doubt -- the 5 V rail divider in
		// particular, where a single point is enough.
		if (cmd.is("one"))
		{
			const uint8_t ch = requireChannel(cmd, out);
			if (ch >= CAL_COUNT)
			{
				return true;
			}
			if (!cmd.has(2))
			{
				out.println("Need the reference value. Example: one rail 4.602");
				return true;
			}

			const float known = cmd.number(2);
			const float raw = readRawCalChannel(sensors, ch, samples_);
			if (isnan(raw))
			{
				out.println("Read failed. Device not responding.");
				return true;
			}
			if (fabsf(raw) < 1e-6f)
			{
				out.println("Reading is zero. A single-point gain needs a non-zero stimulus.");
				return true;
			}

			const float gain = known / raw;
			if (isnan(gain) || gain == 0.0f || fabsf(gain) > 1000.0f)
			{
				out.println("Implausible gain. Check the reference value.");
				return true;
			}

			cal.ch[ch].gain = gain;
			cal.ch[ch].offset = 0.0f;
			out.print("One-point ");
			out.print(calChannelName(ch));
			out.print(": measured ");
			printValue(out, raw);
			out.print(" against ");
			printValue(out, known);
			printGainOffset(out, cal.ch[ch]);
			out.println("  (not saved yet)");
			return true;
		}

		if (cmd.is("fit"))
		{
			const uint8_t ch = requireChannel(cmd, out);
			if (ch >= CAL_COUNT)
			{
				return true;
			}

			ChannelCal fitted;
			if (!calFit(points_[ch], fitted))
			{
				out.println("Fit failed. Need both points and two distinct readings.");
				return true;
			}

			cal.ch[ch] = fitted;
			out.print("Fit ");
			out.print(calChannelName(ch));
			printGainOffset(out, fitted);
			out.println("  (not saved yet)");
			return true;
		}

		if (cmd.is("set"))
		{
			const uint8_t ch = requireChannel(cmd, out);
			if (ch >= CAL_COUNT)
			{
				return true;
			}
			if (!cmd.has(3))
			{
				out.println("Usage: set <chan> <gain> <offset>");
				return true;
			}

			const float gain = cmd.number(2);
			if (gain == 0.0f || isnan(gain))
			{
				out.println("Gain must be non-zero.");
				return true;
			}

			cal.ch[ch].gain = gain;
			cal.ch[ch].offset = cmd.number(3);
			out.print("Set ");
			out.print(calChannelName(ch));
			printGainOffset(out, cal.ch[ch]);
			out.println("  (not saved yet)");
			return true;
		}

		if (cmd.is("clr"))
		{
			const uint8_t ch = requireChannel(cmd, out);
			if (ch < CAL_COUNT)
			{
				cal.ch[ch] = ChannelCal();
				points_[ch] = CalPoints();
				out.print("Cleared ");
				out.println(calChannelName(ch));
			}
			return true;
		}

		if (cmd.is("clrall"))
		{
			for (uint8_t i = 0; i < CAL_COUNT; i++)
			{
				cal.ch[i] = ChannelCal();
				points_[i] = CalPoints();
			}
			out.println("All channels back to unity gain and zero offset (not saved yet)");
			return true;
		}

		if (cmd.is("save"))
		{
			out.println(calSave(cal) ? "Calibration saved" : "Calibration save FAILED");
			return true;
		}

		if (cmd.is("load"))
		{
			out.println(calLoad(cal) ? "Calibration loaded" : "No valid record. Using defaults.");
			printTable(out, cal, sensors);
			return true;
		}

		if (cmd.is("erase"))
		{
			out.println(calErase(cal) ? "Calibration erased" : "Calibration erase FAILED");
			return true;
		}

		out.print("Unknown calibration command: ");
		out.println(cmd.argv[0]);
		return true;
	}

	void printChannels(Stream &out) const
	{
		out.print("Channels:");
		for (uint8_t i = 0; i < CAL_COUNT; i++)
		{
			out.print(" ");
			out.print(calChannelName(i));
		}
		out.println();
	}

	void printHelp(Stream &out) const
	{
		out.println("Calibration commands:");
		out.println("  list                    show gain/offset and live readings");
		out.println("  raw <chan>              averaged uncorrected + corrected reading");
		out.println("  lo <chan> <reference>   record the low point");
		out.println("  hi <chan> <reference>   record the high point");
		out.println("  fit <chan>              solve gain/offset from the two points");
		out.println("  one <chan> <reference>  single-point gain only, offset forced to 0");
		out.println("  set <chan> <g> <o>      write gain/offset directly");
		out.println("  clr <chan> / clrall     back to unity gain and zero offset");
		out.println("  avg [n]                 samples averaged per reading");
		out.println("  save / load / erase     data flash record");
		out.println("  x                       leave calibration mode");
		printChannels(out);
		out.println("Units: ce re cell inav rail in V; we in A; inai in mA");
	}

	void printTable(Stream &out, const BoardCal &cal, const SensorState &sensors)
	{
		out.println("chan   gain        offset      raw          corrected    pts");
		for (uint8_t i = 0; i < CAL_COUNT; i++)
		{
			const float raw = readRawCalChannel(sensors, i, samples_);

			out.print(calChannelName(i));
			padTo(out, strlen(calChannelName(i)), 7);

			printField(out, cal.ch[i].gain, 6, 12);
			printField(out, cal.ch[i].offset, 6, 12);
			printField(out, raw, 5, 13);
			printField(out, applyCal(cal.ch[i], raw), 5, 13);

			out.print(points_[i].hasLow ? "L" : "-");
			out.print(points_[i].hasHigh ? "H" : "-");
			out.print(" ");
			out.println(calChannelUnit(i));
		}

		// The gains share the record, so `save` here writes them too.
		out.print("PID kp = ");
		out.print(cal.pid.kp, 5);
		out.print(" ki = ");
		out.print(cal.pid.ki, 5);
		out.print(" kd = ");
		out.println(cal.pid.kd, 5);
	}

private:
	uint8_t requireChannel(const ParsedCommand &cmd, Stream &out) const
	{
		if (!cmd.has(1))
		{
			out.println("Need a channel name.");
			return CAL_COUNT;
		}
		const uint8_t ch = calChannelByName(cmd.argv[1]);
		if (ch >= CAL_COUNT)
		{
			out.print("Unknown channel: ");
			out.println(cmd.argv[1]);
		}
		return ch;
	}

	static void printValue(Stream &out, float value)
	{
		if (isnan(value)) out.print("nan");
		else out.print(value, 6);
	}

	static void printGainOffset(Stream &out, const ChannelCal &c)
	{
		out.print(": gain = ");
		out.print(c.gain, 6);
		out.print(" offset = ");
		out.print(c.offset, 6);
	}

	static void padTo(Stream &out, size_t written, size_t width)
	{
		for (size_t i = written; i < width; i++) out.print(' ');
	}

	static void printField(Stream &out, float value, uint8_t decimals, size_t width)
	{
		char buf[24];
		if (isnan(value))
		{
			strcpy(buf, "nan");
		}
		else
		{
			snprintf(buf, sizeof(buf), "%.*f", (int)decimals, (double)value);
		}
		out.print(buf);
		padTo(out, strlen(buf), width);
	}

	bool active_ = false;
	uint8_t samples_ = EcritHatConfig::CAL_DEFAULT_SAMPLES;
	CalPoints points_[CAL_COUNT];
};
