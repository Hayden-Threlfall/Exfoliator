#include "ClearCore.h"
#include <math.h>
#include <AutoPID.h>

#define HEATER_PIN ConnectorIO0  // Use ConnectorIO0 instead of IO0
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
    
    // Configure ConnectorIO0 for PWM output
    ConnectorIO0.Mode(Connector::OUTPUT_PWM);
    
    // Initialize PID - faster response for low thermal mass
    PID.setBangBang(0.2);        // Tighter deadband for precision
    PID.setTimeStep(100);        // 100ms for fast-responding thermal systems
    
    Serial.println("Heater setup complete - PWM mode on ConnectorIO0");
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
    ConnectorIO0.State(0);  // Turn off PWM output using State() method
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
    
    // Only run heater if target is set and thermal checks pass
    if (targetTemp > 0 && thermalCheck(inputTemp)) {
        PID.run();
        
        // Convert PID output (0-255) to PWM duty cycle percentage (0-100)
        // ClearCore PWM expects 0-100% duty cycle
        double pwmPercent = constrain((outputValue * 100.0) / 255.0, 0, 100);
        
        // Apply PWM output to heater
        ConnectorIO0.State(pwmPercent);
        
        // Debug output every 5 seconds
        static unsigned long lastDebugOutput = 0;
        if (millis() - lastDebugOutput > 5000) {
            Serial.print("Temp: ");
            Serial.print(inputTemp, 1);
            Serial.print("°C | Target: ");
            Serial.print(targetTemp, 1);
            Serial.print("°C | PWM: ");
            Serial.print(pwmPercent, 1);
            Serial.print("% | PID Output: ");
            Serial.print(outputValue);
            Serial.print("/255 | Error: ");
            Serial.print(targetTemp - inputTemp, 2);
            Serial.println("°C");
            
            lastDebugOutput = millis();
        }
    } else {
        // Turn off heater if no target set or thermal check failed
        ConnectorIO0.State(0);
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