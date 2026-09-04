#include "KD3000.hpp"
#include <Arduino.h>
#include <stdio.h>
#include <stdlib.h>

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
	clearInputBuffer();
	INTERFACE.write(command);
	INTERFACE.write('\n');
	INTERFACE.flush();
	delay(KD3000_BASE_RESPONSE_DELAY_MS);

	size_t index = 0;
	unsigned long deadline = millis() + KD3000_QUERY_TIMEOUT_MS;

	while ((long)(deadline - millis()) > 0)
	{
		while (INTERFACE.available() > 0)
		{
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
		}
	}

	response[index] = '\0';
	return index;
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

KD3000Status getStatus()
{
	KD3000Status status = {0};
	status.raw = (uint8_t)queryLong("STATUS?");
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
