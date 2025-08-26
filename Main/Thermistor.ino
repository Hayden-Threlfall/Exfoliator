#include "ClearCore.h"
#include <math.h>

// Configuration for 104GT-2 with 37kOhm pull-down resistor external and 30kOhm internal to the ClearCore
#define THERMISTOR_INPUT ConnectorA12

// --- Thermistor Setup ---
const float VIN = 24.0;
const float VMAX = 10.0;
const float R_TOP = 37000.0;      // External series resistor
const float R_PULLDOWN = 30000.0; // Internal pull-down resistor inside controller
const float R0 = 100000.0;        // 104GT-2 or NTC 100kohm resistance at 25°C
const float BETA = 3950.0;        // Beta coefficient

void thermistorSetup() {
  THERMISTOR_INPUT.Mode(Connector::INPUT_ANALOG);
  Serial.println("Thermistor initialized.");
}

float getThermistor() {
    float vOut = THERMISTOR_INPUT.AnalogVoltage();

    // Safety check
    if (vOut <= 0.01 || vOut >= VMAX - 0.01) {
        Serial.println("Voltage out of range");
        return -1.0;
    }

    // Calculate resistance
    float R_bottom = R_TOP * vOut / (VIN - vOut);

    // Check thermistor resistance
    if (R_bottom >= R_PULLDOWN) {
        Serial.println("R_bottom out of range");
        return -1.0;
    }
    float R_thermistor = (R_bottom * R_PULLDOWN) / (R_PULLDOWN - R_bottom);

    // Steinhart-Hart Beta formula
    float steinhart;
    steinhart = log(R_thermistor / R0);
    steinhart /= BETA;
    steinhart += 1.0 / 298.15;
    steinhart = 1.0 / steinhart;
    float temperatureC = steinhart - 273.15;

    // Debugging output
    //sprintf(buffer, "Vout: %.3f V, R_bottom: %.1f Ω, R_thermistor: %.1f Ω, Temp: %.2f °C", vOut, R_bottom, R_thermistor, temperatureC);
    //Serial.println(buffer);

    return temperatureC;
}
