#include <pwm.h>

// Pin for PWM voltage output
#define V_OUT 6
// Pin for current sensor input
#define I_IN A1
#define V_IN A2

#define STEP_MS 50

// the output voltage (V)
float outputVoltage = 0.5;
// the argument value from the serial command
float argumentValue = 0;
// the target current (mA) in current mode
float targetCurrent = 10;
// the target voltage (V) in voltage mode
float targetVoltage = 0.5;

// PID constants
float kp = 0.01;    // proportional gain
float ki = 0.001;   // integral gain
float kd = 0.0001;  // derivative gain

// PID variables
float integral = 0;
float previousError = 0;
unsigned long previousTime = 0;

// the status of the system
bool active = false;
// the mode of the system
bool currentMode = false;

String command;
PwmOut pwm(V_OUT);

void setup() 
{
	Serial.begin(9600);
	pinMode(V_OUT, OUTPUT);
	pinMode(LED_BUILTIN, OUTPUT);

	// Specific to Uno R4
	analogWriteResolution(12);
	analogReadResolution(14);

	pwm.begin(980.0f, 0.0f);
}

void resetPID()
{
	// Reset PID variables
	integral = 0;
	previousError = 0;
	previousTime = 0;
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
		// Reset PID variables when switching to current mode
		resetPID();
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
		resetPID();
		Serial.println("Reset");
	}
	else if (command == "f")
	{
		// Turn off Output
		active = false;
		resetPID();
		Serial.println("Turn off");
		//analogWrite(V_OUT, 0);
		pwm.pulse_perc(0);
	}

	// Update status LED
	digitalWrite(LED_BUILTIN, active);

	// skip the loop if not active
	if (!active)
	{
		return;  
	} 
 
	// output
	float output = (outputVoltage / 5.0) * 100.0;
	pwm.pulse_perc(output);
	//give it some time for the system to react
	delay(STEP_MS);

	// read current value
	int sensorValue = analogRead(I_IN);
	float current = 1000 * ( sensorValue / 16383.0 ) * 0.5;

  int voltageValue = analogRead(V_IN);
  float actualVoltage = (voltageValue / 16383.0 ) * 5.0;


	// adjust the voltage to hold current in current mode
	if (currentMode)
	{
		// PID controller implementation
		unsigned long currentTime = millis();
		float deltaTime = (currentTime - previousTime) / 1000.0; // Convert to seconds
		
		if (previousTime == 0) {
			deltaTime = STEP_MS / 1000.0; // Use STEP_MS for first iteration
		}
		
		float error = targetCurrent - current;
		
		// Proportional term
		float proportional = kp * error;
		
		// Integral term (with windup protection)
		integral += error * deltaTime;
		// Prevent integral windup by clamping
		integral = constrain(integral, -100.0, 100.0);
		float integralTerm = ki * integral;
		
		// Derivative term
		float derivative = 0;
		if (deltaTime > 0) {
			derivative = (error - previousError) / deltaTime;
		}
		float derivativeTerm = kd * derivative;
		
		// Calculate PID output
		float pidOutput = proportional + integralTerm + derivativeTerm;
		
		// Apply PID output to voltage
		outputVoltage += pidOutput;
		
		// Update previous values for next iteration
		previousError = error;
		previousTime = currentTime;
		
		// limit the output voltage to between 0 and 5V
		outputVoltage = constrain(outputVoltage, 0, 5);
	}

	Serial.print(current, 4);
	Serial.print(",");
	Serial.print(outputVoltage, 3);
	Serial.print(",");
  Serial.println(actualVoltage, 3);
}
