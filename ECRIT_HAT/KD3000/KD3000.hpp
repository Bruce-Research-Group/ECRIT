#ifndef KD3000_H
#define KD3000_H

#include <Arduino.h>

// just one channel
#define CH "1"
#define INTERFACE Serial1

/**
Command format ：VSET<X>:<NR2>
1. VSET: command header
2. X: output channel
3. : separator
4. NR2: parameter
Command Details:
1. ISET<X>:<NR2>
Description： Sets the output current.
Example:ISET1:2.225
Response time 50ms
Sets the CH1 output current to 2.225A
2. ISET<X>?
Description： Returns the output current setting.
Example: ISET1?
Returns the CH1 output current setting.
3. VSET<X>:<NR2>
Description：Sets the output voltage.
Example VSET1:20.50
Sets the CH1 voltage to 20.50V
4. VSET<X>?
Description：Returns the output voltage setting.
Example VSET1?
Returns the CH1 voltage setting
5. IOUT<X>?
Description：Returns the actual output current.
Example IOUT1?
Returns the CH1 output current
6. VOUT<X>?
Description：Returns the actual output voltage.
Example VOUT1?
Returns the CH1 output voltage
7. OUT<Boolean>
Description：Turns on or off the output.
Boolean：0 OFF,1 ON
Example: OUT1 Turns on the output
8. STATUS?
Description：Returns the POWER SUPPLY status.
Contents 8 bits in the following format
Bit Item Description
0 CH1 0=CC mode, 1=CV mode
1,2,3,4,5 N/A
6 Output 0=Off, 1=On
7 N/AN/A
9. *IDN?
Description：Returns the KA3005P identification.
Example *IDN?
Contents KORAD KD3005P V2.0 (Manufacturer, model
name,).
10. RCL<NR1>
Description：Recalls a panel setting.
NR1 1 5: Memory number 1 to 5
Example RCL1 Recalls the panel setting stored in
memory number 1
11. SAV<NR1>
Description：Stores the panel setting.
NR1 1 5: Memory number 1 to 5
Example ： SAV1 Stores the panel setting in memory
number 1
12. OCP<NR1>
Description：Over current
Example ：OCP1 OCP ON
 */

enum KD3000StatusBit : uint8_t
{
	KD3000_STATUS_CV_MODE_BIT = 0,
	KD3000_STATUS_OUTPUT_ON_BIT = 6,
};

enum KD3000StatusMask : uint8_t
{
	KD3000_STATUS_CV_MODE_MASK = (1 << KD3000_STATUS_CV_MODE_BIT),
	KD3000_STATUS_OUTPUT_ON_MASK = (1 << KD3000_STATUS_OUTPUT_ON_BIT),
};

struct KD3000Status
{
	uint8_t raw; // STATUS? response byte, bits follow the protocol table above

	bool cvMode() const { return (raw & KD3000_STATUS_CV_MODE_MASK) != 0; }
	bool outputOn() const { return (raw & KD3000_STATUS_OUTPUT_ON_MASK) != 0; }
};


// raw helper functions
void set(const char *command);
size_t query(const char *command, char *response, size_t responseSize);

void setCurrent(float current);
float getCurrentSetting();
void setVoltage(float voltage);
float getVoltageSetting();
float getCurrent();
float getVoltage();
void setOutput(bool on);
KD3000Status getStatus();
bool getSerialNumber(char *serialNumber, size_t serialNumberSize);
void recallPanelSetting(uint8_t memoryNumber);
void savePanelSetting(uint8_t memoryNumber);
void setOverCurrentProtection(bool on);

#endif // KD3000_H