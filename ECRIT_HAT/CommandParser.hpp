#pragma once

#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

// Line-buffered console parser.
//
// Serial_PSU accepted "<letter> [number]" only. The calibration console needs
// more than that, so this version tokenises the whole line while keeping the
// legacy fields intact: `code` and `arg` still mean what they meant, so the
// host UI (SendCommandSerial.py) keeps working unchanged.

static constexpr uint8_t CMD_MAX_TOKENS = 6;

struct ParsedCommand
{
	char code = '\0';  // first character of token 0, if token 0 is one char
	bool hasArg = false;
	float arg = 0.0f;  // numeric value of token 1, if present

	uint8_t argc = 0;
	const char *argv[CMD_MAX_TOKENS] = {nullptr};

	// Case-insensitive compare of the command word.
	bool is(const char *word) const
	{
		if (argc == 0) return false;
		const char *a = argv[0];
		const char *b = word;
		while (*a && *b)
		{
			if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) return false;
			a++;
			b++;
		}
		return *a == '\0' && *b == '\0';
	}

	const char *token(uint8_t index) const
	{
		return (index < argc) ? argv[index] : nullptr;
	}

	// Numeric value of token `index`, or `fallback` if it is missing.
	float number(uint8_t index, float fallback = 0.0f) const
	{
		const char *t = token(index);
		return (t != nullptr) ? (float)atof(t) : fallback;
	}

	bool has(uint8_t index) const { return index < argc; }
};

class CommandReader
{
public:
	bool poll(Stream &serial, ParsedCommand &out)
	{
		while (serial.available() > 0)
		{
			const char c = (char)serial.read();
			if (c == '\r')
			{
				continue;
			}

			if (c == '\n')
			{
				if (len_ == 0)
				{
					continue;
				}

				buffer_[len_] = '\0';
				len_ = 0;
				return parseLine(buffer_, out);
			}

			if (len_ < (sizeof(buffer_) - 1))
			{
				buffer_[len_++] = c;
			}
		}

		return false;
	}

private:
	// Tokenises in place. The returned pointers stay valid until the next
	// poll() that completes a line, which is always after the caller has
	// handled this command.
	static bool parseLine(char *line, ParsedCommand &cmd)
	{
		cmd = ParsedCommand();

		char *p = line;
		while (*p != '\0' && cmd.argc < CMD_MAX_TOKENS)
		{
			while (*p == ' ' || *p == '\t') p++;
			if (*p == '\0') break;

			cmd.argv[cmd.argc++] = p;

			while (*p != '\0' && *p != ' ' && *p != '\t') p++;
			if (*p != '\0')
			{
				*p = '\0';
				p++;
			}
		}

		if (cmd.argc == 0)
		{
			return false;
		}

		if (strlen(cmd.argv[0]) == 1)
		{
			cmd.code = cmd.argv[0][0];
		}

		if (cmd.argc >= 2)
		{
			cmd.hasArg = true;
			cmd.arg = (float)atof(cmd.argv[1]);
		}

		return true;
	}

	char buffer_[80] = {0};
	size_t len_ = 0;
};
