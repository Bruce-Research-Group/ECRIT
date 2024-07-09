// Pin for PWM voltage output
#define V_OUT 6
// Pin for current sensor input
#define I_IN A1

// the step size for adjusting the output voltage (V) in current mode
float intervalSize = 0.01;
// the output voltage (V)
float outputVoltage = 0.5;
// the argument value from the serial command
float argumentValue = 0;
// the target current (mA) in current mode
float targetCurrent = 10;
// the target voltage (V) in voltage mode
float targetVoltage = 0.5;

// the status of the system
bool active = false;
// the mode of the system
bool currentMode = false;

String command;

void setup() 
{
	Serial.begin(9600);
	pinMode(V_OUT, OUTPUT);
	pinMode(LED_BUILTIN, OUTPUT);
}

void loop() 
{
	// save serial command
	command = "";
	while (Serial.available())
	{
		delay(3);
		if (Serial.available() > 0)
		{
			char c = Serial.read();
			if (c == '\n')
			{
				break;  
			}
			else if (c != ' ')
			{
				command += c;
			}
			else // if it is space, we parse the next float
			{
				argumentValue = Serial.parseFloat();
			}
		}  
	}

	// parse command
	if (command == "c")
	{
		// Hold Current Mode
		active = true;
		currentMode = true;
		targetCurrent = argumentValue;
		Serial.print("Hold Current, target = ");
		Serial.print(targetCurrent);
		Serial.println(" mA");
	}
	else if (command == "v")
	{
		// Constant Voltage Mode
		active = true;
		currentMode = false;
		outputVoltage = argumentValue;
		Serial.print("Hold Voltage, target = ");
		Serial.print(outputVoltage);
		Serial.println(" V");
	}
	else if (command == "r")
	{
		// Reset Output Voltage
		outputVoltage = 0.5;
		Serial.println("Reset");
	}
	else if (command == "f")
	{
		// Turn off Output
		active = false;
		Serial.println("Turn off");
		analogWrite(V_OUT, 0);
	}

	// Update status LED
	digitalWrite(LED_BUILTIN, active);

	// skip the loop if not active
	if (!active)
	{
		return;  
	} 

	// output
	int output = ( outputVoltage / 5 ) * 255;
	analogWrite(V_OUT, output);
	//give it some time for the system to react
	delay(50);

	// read current value
	int sensorValue = analogRead(I_IN);
	float current = 1000 * ( sensorValue / 1023.0 ) * 0.5;

	// adjust the voltage to hold current in current mode
	if (currentMode)
	{
		// adjust the output voltage base on the current
		if (current < targetCurrent)
		{
			outputVoltage += intervalSize;  
		}
		else if (current > targetCurrent)
		{
			outputVoltage -= intervalSize;
		}
		// limit the output voltage to between 0 and 5V
		outputVoltage = constrain(outputVoltage, 0, 5);
	}

	Serial.print("S: ");
	Serial.print(current);
	Serial.print(" mA, ");
	Serial.print(outputVoltage);
	Serial.println(" V");
}
