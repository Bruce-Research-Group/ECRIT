#pragma once

#include <Arduino.h>

class PidController
{
public:
	float kp = 0.10f;
	float ki = 0.10f;
	float kd = 0.001f;

	void reset()
	{
		integral_ = 0.0f;
		previousError_ = 0.0f;
		previousTimeMs_ = 0;
	}

	float step(float target, float measurement, unsigned long nowMs, unsigned long stepMs)
	{
		float deltaTime = (nowMs - previousTimeMs_) / 1000.0f;
		if (previousTimeMs_ == 0)
		{
			deltaTime = stepMs / 1000.0f;
		}

		const float error = target - measurement;

		const float proportional = kp * error;

		integral_ += error * deltaTime;
		integral_ = clampFloat(integral_, -100.0f, 100.0f);
		const float integralTerm = ki * integral_;

		float derivative = 0.0f;
		if (deltaTime > 0.0f)
		{
			derivative = (error - previousError_) / deltaTime;
		}
		const float derivativeTerm = kd * derivative;

		previousError_ = error;
		previousTimeMs_ = nowMs;

		return proportional + integralTerm + derivativeTerm;
	}

private:
	static float clampFloat(float value, float lo, float hi)
	{
		if (value < lo) return lo;
		if (value > hi) return hi;
		return value;
	}

	float integral_ = 0.0f;
	float previousError_ = 0.0f;
	unsigned long previousTimeMs_ = 0;
};
