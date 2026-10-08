#include "KD3000.hpp"
#include <Arduino.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const unsigned long KD3000_BASE_RESPONSE_DELAY_MS = 50;
static const unsigned long KD3000_QUERY_TIMEOUT_MS = 300;
static const unsigned long KD3000_INTER_CHAR_GRACE_MS = 20;
static const size_t KD3000_RESPONSE_BUFFER_SIZE = 64;

static void clearInputBuffer()
{
	while (INTERFACE.available() > 0)
	{
		INTERFACE.read();
	}
}

// The one query beginQuery() may have in flight. See pollQuery().
static struct
{
	bool active;
	bool rawByte;
	unsigned long sentMs;
	unsigned long lastByteMs;
	size_t index;
	char buffer[KD3000_RESPONSE_BUFFER_SIZE];
} pending = {};

void cancelQuery()
{
	pending.active = false;
}

bool queryInFlight()
{
	return pending.active;
}

static float queryFloat(const char *command)
{
	char response[KD3000_RESPONSE_BUFFER_SIZE];
	query(command, response, sizeof(response));
	return (float)atof(response);
}

static long queryLong(const char *command)
{
	char response[KD3000_RESPONSE_BUFFER_SIZE];
	query(command, response, sizeof(response));
	return atol(response);
}

void set(const char *command)
{
	// Clearing the input would eat the reply to a query in flight anyway.
	cancelQuery();
	clearInputBuffer();
	INTERFACE.write(command);
	INTERFACE.write('\n');
	INTERFACE.flush();
	// delay(KD3000_BASE_RESPONSE_DELAY_MS);
}

size_t query(const char *command, char *response, size_t responseSize)
{
	if (response == NULL || responseSize == 0)
	{
		return 0;
	}

	response[0] = '\0';
	cancelQuery();
	clearInputBuffer();
	INTERFACE.write(command);
	INTERFACE.write('\n');
	INTERFACE.flush();
	delay(KD3000_BASE_RESPONSE_DELAY_MS);

	size_t index = 0;
	// Two deadlines. `deadline` is the idle timeout that the inter-character
	// grace pushes forward; `hardDeadline` is the absolute cap that the grace
	// may never push past.
	//
	// Both are needed. The inner drain loop below runs while bytes keep
	// arriving, so it has to test a deadline itself -- otherwise a line that
	// never goes idle traps us there and the outer test is never reached. And
	// the grace has to be capped, because a source delivering a byte more
	// often than KD3000_INTER_CHAR_GRACE_MS -- at 9600 baud that is every
	// single character -- renews the idle timeout indefinitely. Without both,
	// a babbling or noisy RX input hangs query() forever, and since
	// probePsuOnce() runs from setup(), it hangs the sketch before `Ready`
	// and takes the USB console down with it.
	//
	// The cap restores what PsuControl.hpp already documents: "a query that
	// gets no answer costs 350 ms" -- the 50 ms settle plus this timeout.
	const unsigned long hardDeadline = millis() + KD3000_QUERY_TIMEOUT_MS;
	unsigned long deadline = hardDeadline;

	while ((long)(deadline - millis()) > 0)
	{
		while (INTERFACE.available() > 0)
		{
			if ((long)(hardDeadline - millis()) <= 0)
			{
				break;
			}

			const char ch = (char)INTERFACE.read();

			if (ch == '\r' || ch == '\n')
			{
				if (index > 0)
				{
					response[index] = '\0';
					return index;
				}
				continue;
			}

			if ((index + 1) < responseSize)
			{
				response[index++] = ch;
			}

			deadline = millis() + KD3000_INTER_CHAR_GRACE_MS;
			if ((long)(deadline - hardDeadline) > 0)
			{
				deadline = hardDeadline;
			}
		}

		if ((long)(hardDeadline - millis()) <= 0)
		{
			break;
		}
	}

	response[index] = '\0';
	return index;
}

void beginQuery(const char *command, bool rawByte)
{
	cancelQuery();
	clearInputBuffer();
	INTERFACE.write(command);
	INTERFACE.write('\n');
	INTERFACE.flush();

	pending.active = true;
	pending.rawByte = rawByte;
	pending.sentMs = millis();
	pending.lastByteMs = 0;
	pending.index = 0;
}

// The same end-of-reply rules as query(): a text reply ends at CR or LF, or
// KD3000_INTER_CHAR_GRACE_MS after its last byte, since this supply sends no
// terminator. A raw reply (STATUS?) is the first byte, whatever its value --
// see queryStatusByte(). Either one gives up KD3000_BASE_RESPONSE_DELAY_MS +
// KD3000_QUERY_TIMEOUT_MS after the command, which is what a blocking query()
// that got no answer cost. There is no fixed settle delay: the bytes are
// collected as they arrive.
KD3000PollResult pollQuery(char *response, size_t responseSize)
{
	if (!pending.active)
	{
		return KD3000_POLL_CANCELLED;
	}

	const unsigned long now = millis();
	bool terminated = false;
	while (!terminated && INTERFACE.available() > 0)
	{
		const char ch = (char)INTERFACE.read();
		if (pending.rawByte)
		{
			if (responseSize > 0) response[0] = ch;
			pending.active = false;
			return KD3000_POLL_DONE;
		}
		if (ch == '\r' || ch == '\n')
		{
			terminated = pending.index > 0;
			continue;
		}
		if ((pending.index + 1) < sizeof(pending.buffer))
		{
			pending.buffer[pending.index++] = ch;
		}
		pending.lastByteMs = now;
	}

	if (pending.index > 0 &&
	    (terminated || (long)(now - pending.lastByteMs) >= (long)KD3000_INTER_CHAR_GRACE_MS))
	{
		if (responseSize > 0)
		{
			const size_t n = (pending.index < responseSize - 1) ? pending.index : responseSize - 1;
			memcpy(response, pending.buffer, n);
			response[n] = '\0';
		}
		pending.active = false;
		return KD3000_POLL_DONE;
	}

	if ((long)(now - pending.sentMs) >= (long)(KD3000_BASE_RESPONSE_DELAY_MS + KD3000_QUERY_TIMEOUT_MS))
	{
		pending.active = false;
		return KD3000_POLL_TIMEOUT;
	}
	return KD3000_POLL_PENDING;
}

void setCurrent(float current)
{
	char command[24];
	snprintf(command, sizeof(command), "ISET%s:%.3f", CH, current);
	set(command);
}

float getCurrentSetting()
{
	char command[16];
	snprintf(command, sizeof(command), "ISET%s?", CH);
	return queryFloat(command);
}

void setVoltage(float voltage)
{
	char command[24];
	snprintf(command, sizeof(command), "VSET%s:%.2f", CH, voltage);
	set(command);
}

float getVoltageSetting()
{
	char command[16];
	snprintf(command, sizeof(command), "VSET%s?", CH);
	return queryFloat(command);
}

float getCurrent()
{
	char command[16];
	snprintf(command, sizeof(command), "IOUT%s?", CH);
	return queryFloat(command);
}

float getVoltage()
{
	char command[16];
	snprintf(command, sizeof(command), "VOUT%s?", CH);
	return queryFloat(command);
}

void setOutput(bool on)
{
	set(on ? "OUT1" : "OUT0");
}

// Read the STATUS? byte.
//
// This deliberately does not go through query(), for two independent reasons,
// both of which silently produced a wrong answer rather than an error:
//
//   - query() treats CR and LF as end-of-response. The status byte is binary,
//     so 0x0A and 0x0D are legal values, and query() would swallow them as
//     terminators and report an empty reply.
//
//   - the caller then ran the text through atol(). The two most common replies
//     from this supply are '@' (0x40, output on, CC) and 'A' (0x41, output on,
//     CV); atol() maps both to 0, which reads back as CC mode with the output
//     off. That is why the supply appeared to be permanently in CC with the
//     output off even while it was visibly delivering current.
//
// There is no fixed settle delay here: waiting on available() with a deadline
// covers the manual's 50 ms response time and returns as soon as the byte
// lands. Any trailing terminator is left in the buffer for the next command's
// clearInputBuffer() to discard, which is what every other call already does.
bool queryStatusByte(uint8_t &out)
{
	cancelQuery();
	clearInputBuffer();
	INTERFACE.write("STATUS?");
	INTERFACE.write('\n');
	INTERFACE.flush();

	const unsigned long deadline = millis() + KD3000_QUERY_TIMEOUT_MS;
	while (INTERFACE.available() <= 0)
	{
		if ((long)(deadline - millis()) <= 0)
		{
			return false;
		}
	}

	out = (uint8_t)INTERFACE.read();
	return true;
}

KD3000Status getStatus()
{
	KD3000Status status = {0};
	uint8_t raw = 0;
	if (queryStatusByte(raw))
	{
		status.raw = raw;
	}
	return status;
}

bool getSerialNumber(char *serialNumber, size_t serialNumberSize)
{
	return query("*IDN?", serialNumber, serialNumberSize) > 0;
}

void recallPanelSetting(uint8_t memoryNumber)
{
	if (memoryNumber < 1)
	{
		memoryNumber = 1;
	}
	else if (memoryNumber > 5)
	{
		memoryNumber = 5;
	}

	char command[8];
	snprintf(command, sizeof(command), "RCL%u", (unsigned int)memoryNumber);
	set(command);
}

void savePanelSetting(uint8_t memoryNumber)
{
	if (memoryNumber < 1)
	{
		memoryNumber = 1;
	}
	else if (memoryNumber > 5)
	{
		memoryNumber = 5;
	}

	char command[8];
	snprintf(command, sizeof(command), "SAV%u", (unsigned int)memoryNumber);
	set(command);
}

void setOverCurrentProtection(bool on)
{
	set(on ? "OCP1" : "OCP0");
}
