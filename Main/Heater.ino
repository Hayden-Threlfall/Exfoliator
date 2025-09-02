#include "ClearCore.h"
#include <math.h>
#include <AutoPID.h>

#define heaterADCResolution 12
#define heater ConnectorIO5

// Time-Proportional Control (TPC) settings
// This is the total cycle time for one on/off period of the SSR.
const unsigned long TPC_CYCLE_TIME = 500; 
const double OVERSHOOT_CUTOFF = 5.0;   // °C above target that forces immediate off
const double NEAR_TARGET_WINDOW = 20.0; // °C window considered "near" the target
const double NEAR_TARGET_DUTY_MAX_MULTIPLIER = .5; // max outputValue (0-255) when near target

bool heaterOn = false;
unsigned long heaterTimer = 0;
unsigned long cycleStartTime = 0;
double lastTemp = 0.0;
bool thermalRunAway = false;
double targetTemp = 0;      // target temperature (°C)
double inputTemp = 0.0;     // current temperature
double outputValue = 0.0;   // output (0-255)
double Kp = 0.15, Ki = 0.0, Kd = 2.0;
AutoPID PID(&inputTemp, &targetTemp, &outputValue, 0, 255, Kp, Ki, Kd);

void heaterSetup() {
    analogReadResolution(heaterADCResolution);
    heater.Mode(Connector::OUTPUT_DIGITAL); 
    heater.State(false); // start off
    PID.setBangBang(0.25); // 0.5°C deadband
    PID.setTimeStep(250); // PID calc every 100ms
    heaterOff();
    thermalRunAway = false;
}

void setTargetTemperature(double temperature) {
    if (temperature > 300) // This may be max temp allowed in code, but due to material limitations ~240c is real max
        temperature = 300;
    if (temperature == 0) {
        heaterOff();
        return;
    }
    targetTemp = temperature;
    lastTemp = getThermistor();
    heaterTimer = millis();
    cycleStartTime = millis(); // Initialize the TPC cycle timer
    heaterOn = true;
}

double getTargetTemperature() {
    return targetTemp;
}

void heaterOff() {
    PID.stop();
    heater.State(false); 
    heaterTimer = 0;
    lastTemp = 0;
    targetTemp = 0;
    heaterOn = false;
}

bool holdPIDCheck() { 
    if (!heaterOn || heaterTimer == 0 || millis() - heaterTimer < 75000) { // check if heater on / 75s grace period to reach temp
        return true;
    }
    if (!PID.atSetPoint(5.0)) {
        Serial.println("Heater Not Holding Temperature");
        client.println("Heater Not Holding Temperature");
        return false;
    }
    return true;
        
}

bool thermalRangeCheck(double temperature) {
    if (temperature > 310.0 || temperature < 12.0) {
        Serial.println("Thermistor Out Of Range");
        client.println("Thermistor Out Of Range");
        return false;
    }
    return true; // safe
}

bool thermalCheck(double temperature) {
        if (!thermalRangeCheck(temperature) ||
            !holdPIDCheck() ||
            thermalRunAway
            ) {
            thermalRunAway = true;
            heaterOff();
            heater.State(false); // Redundant, but just in case
            client.println("Thermal Runaway");
            Serial.println("Thermal Runaway");
            emergencyStop();
            return false;
        }
        return true; // safe
}


void heaterStep() {
    inputTemp = getThermistor();
    if (!thermalCheck(inputTemp))
        return;
    if(heaterOn) {
        PID.run();

        // Lower PWM value to prevent Overshooting
        if (fabs(targetTemp - inputTemp) <= NEAR_TARGET_WINDOW) {
            if (outputValue > targetTemp * NEAR_TARGET_DUTY_MAX_MULTIPLIER) {
                outputValue = targetTemp * NEAR_TARGET_DUTY_MAX_MULTIPLIER;
            }
        }

        // Compute on time for outputValue
        unsigned long onTime = (unsigned long)(outputValue / 255.0 * TPC_CYCLE_TIME);
        unsigned long elapsed = millis() - cycleStartTime;

        if (elapsed < onTime) {
            heater.State(true);
        } else if (elapsed < TPC_CYCLE_TIME) {
            heater.State(false);
        } else {
            cycleStartTime = millis(); // restart cycle, no forced ON
        }
    }
    else
        heaterOff(); // Saftey make sure nothing gets manually overidden 
}

