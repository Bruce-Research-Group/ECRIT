#pragma once

#include <Arduino.h>

struct ParsedCommand
{
	char code = '\0';
	bool hasArg = false;
	float arg = 0.0f;
};

class CommandReader
{
public:
	explicit CommandReader(size_t maxLineLen = 64) : maxLineLen_(maxLineLen) {}

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

				buffer_[minSize(len_, sizeof(buffer_) - 1)] = '\0';
				len_ = 0;
				return parseLine(buffer_, out);
			}

			if (len_ < (sizeof(buffer_) - 1) && len_ < maxLineLen_ - 1)
			{
				buffer_[len_++] = c;
			}
		}

		return false;
	}

private:
	static size_t minSize(size_t a, size_t b) { return (a < b) ? a : b; }

	static bool parseLine(const char *line, ParsedCommand &cmd)
	{
		if (line == nullptr)
		{
			return false;
		}

		const char *p = line;
		while (*p == ' ' || *p == '\t')
		{
			p++;
		}

		if (*p == '\0')
		{
			return false;
		}

		cmd.code = *p++;

		while (*p == ' ' || *p == '\t')
		{
			p++;
		}

		if (*p == '\0')
		{
			cmd.hasArg = false;
			cmd.arg = 0.0f;
			return true;
		}

		cmd.hasArg = true;
		cmd.arg = (float)atof(p);
		return true;
	}

	size_t maxLineLen_;
	char buffer_[64] = {0};
	size_t len_ = 0;
};
