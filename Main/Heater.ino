#include "ClearCore.h"
#include <math.h>
#include <AutoPID.h>

#define HEATER_PIN ConnectorIO5
#define heaterADCResolution 12

unsigned long heaterTimer = 0.0;
double lastTemp;

bool thermalRunAway = false;
double targetTemp = 0;      // target temperature (°C)
double inputTemp = 0.0;     // current temperature
double outputValue = 0.0;   // output (0-255)

// More aggressive PID values for low thermal mass systems
double Kp = 50.0, Ki = 2.0, Kd = 25.0;  // Higher gains for responsive control
AutoPID PID(&inputTemp, &targetTemp, &outputValue, 0, 255, Kp, Ki, Kd);

void heaterSetup() {
    analogReadResolution(heaterADCResolution);
    
    // Configure IO0 for PWM output using Arduino-style pinMode
    HEATER_PIN.Mode(Connector::OUTPUT_PWM);
    
    // Initialize PID - faster response for low thermal mass
    PID.setBangBang(0.2);        // Tighter deadband for precision
    PID.setTimeStep(100);        // 100ms for fast-responding thermal systems
    
    Serial.println("Heater setup complete - PWM mode on IO0");
}

void setTargetTemperature(double temperature) {
    targetTemp = temperature;
    lastTemp = getThermistor();
    heaterTimer = millis();
    
    if (temperature > 0) {
        PID.reset();  // Reset PID integrator when setting new target
        Serial.print("Target temperature set to: ");
        Serial.print(temperature);
        Serial.println("°C");
    }
}

double getTargetTemperature() {
    return targetTemp;
}

void heaterOff() {
    PID.stop();
    HEATER_PIN.PwmDuty(0);
    heaterTimer = 0;
    lastTemp = 0;
    targetTemp = 0;
    Serial.println("Heater turned off");
}

bool holdPIDCheck() { 
    return(PID.atSetPoint(2.0)); // Check if within +-2°C of target (tighter tolerance)
}

bool thermalRisingCheck(double temperature) { 
    if (checkTimer(heaterTimer, 15000) && !holdPIDCheck()) {  // Check every 15 seconds
        if (temperature - lastTemp > 3.0) {  // Reduced threshold
            lastTemp = temperature;
            heaterTimer = millis();  // Reset timer
            return true;
        } else {
            Serial.println("Warning: Temperature not rising sufficiently");
            return false;
        }
    }
    return true;
}

bool thermalRunawayCheck(double temperature) { 
    if (temperature > 280.0 || temperature < 12.0) {
        heaterOff();
        thermalRunAway = true;
        Serial.print("THERMAL RUNAWAY: Temperature out of range: ");
        Serial.print(temperature);
        Serial.println("°C");
        return false;
    }
    return true;
}

bool thermalCheck(double temperature) { 
    if (!thermalRunAway) {
        if (!thermalRunawayCheck(temperature)) {
            return false;
        }
        if (!thermalRisingCheck(temperature)) {
            Serial.println("Thermal check failed - heating ineffective");
            return false;
        }
    }
    return true;
}

void heaterStep() {
    inputTemp = getThermistor();

    if (targetTemp > 0 && thermalCheck(inputTemp)) {
        PID.run();

        // Constrain PID output
        int pwmValue = constrain((int)outputValue, 0, 255);

        // Apply to ClearCore PWM
        HEATER_PIN.PwmDuty((float)pwmValue / 255.0f);

        // Debug every 5 sec
        static unsigned long lastDebugOutput = 0;
        if (millis() - lastDebugOutput > 5000) {
            sprintf(buffer,
                    "Temp: %.1f°C | Target: %.1f°C | PWM: %d/255 (%.1f%%) | Error: %.2f°C", 
                    inputTemp, targetTemp, pwmValue, (pwmValue * 100.0) / 255.0, targetTemp - inputTemp);
            Serial.println(buffer);
            lastDebugOutput = millis();
        }
    }
    else {
        HEATER_PIN.PwmDuty(0.0f);  // Heater off
        if (targetTemp <= 0) {
            PID.stop();
        }
    }
}

// Helper function to tune PID parameters during runtime
void setPIDParameters(double p, double i, double d) {
    Kp = p;
    Ki = i;
    Kd = d;
    PID.setGains(Kp, Ki, Kd);
    Serial.print("PID parameters updated - P:");
    Serial.print(Kp);
    Serial.print(" I:");
    Serial.print(Ki);
    Serial.print(" D:");
    Serial.println(Kd);
}

// Get current PID output for debugging
double getPIDOutput() {
    return outputValue;
}

// Get current PWM percentage
double getPWMPercentage() {
    return (outputValue * 100.0) / 255.0;
}