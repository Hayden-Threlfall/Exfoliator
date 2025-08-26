#include "ClearCore.h"
#include <math.h>
#include <AutoPID.h>

#define HEATER_PIN IO5
#define heaterADCResolution 12

unsigned long heaterTimer = 0.0;
double lastTemp;

bool thermalRunAway = false;
double targetTemp = 0;    // target temperature (°C)
double inputTemp = 0.0;     // current temperature
double outputValue = 0.0;   // output (0-255)
double Kp = 1.0, Ki = 0.5, Kd = 5;  // tuning parameters
AutoPID PID(&inputTemp, &targetTemp, &outputValue, 0, 255, Kp, Ki, Kd);

void heaterSetup() {
    analogReadResolution(heaterADCResolution);
    pinMode(HEATER_PIN, OUTPUT);
    PID.setBangBang(0.5);        // 0.5°C deadband to reduce switching
    PID.setTimeStep(100);      // PID calculation interval (ms)
}

void setTargetTemperature(double temperature) {
  targetTemp = temperature;
  lastTemp = getThermistor();
  heaterTimer = millis();
}

void heaterOff() {
    PID.stop();
    digitalWrite(HEATER_PIN, LOW);
    heaterTimer = 0;
    lastTemp = 0;
    targetTemp = 0;
}
    

bool holdPIDCheck() { //True is good
    return(PID.atSetPoint(5.0)); // Check if Withen +- 5 deg of Target Temperature
}

bool thermalRisingCheck(double temperature) { //True is good
    if (checkTimer(heaterTimer, 20000) && !holdPIDCheck()) {
        if (temperature - lastTemp > 5.0) {
            lastTemp = temperature;
            return true;
        }
        else {
            return false;
        }
            
    }
    return true;
}

bool thermalRunawayCheck(double temperature) { //True is good
    if (temperature > 280.0 || temperature < 12.0) {
        heaterOff();
        Serial.println("Thermistor Out Of Range");
        return true; // If temp above 280 max range or under 12 close to min voltage  
    }
    return false;
}

bool thermalCheck(double temperature) { //True is good
    if (!PID.isStopped() || !thermalRunAway) {
        if (thermalRunawayCheck(temperature) && (holdPIDCheck() || thermalRisingCheck(temperature))) {
            thermalRunAway = true;
            heaterOff();
            Serial.println("Thermal Run Away");
            return false;
        }
    }
    return true;
}

void heaterStep() {
    inputTemp = getThermistor();
    
    if (true) //(thermalRisingCheck(inputTemp)) 
    {
        PID.run();
        // Simple ON/OFF output using threshold
        if (outputValue > 128) {
            digitalWrite(HEATER_PIN, HIGH);
        } else {
            digitalWrite(HEATER_PIN, LOW);
        }
        
        //sprintf(buffer, "Temp: %.1f °C | Target Temp: %.1f °C | PID Output: %.2f", inputTemp, targetTemp, outputValue);
        //Serial.println(buffer);
    }

    
}
