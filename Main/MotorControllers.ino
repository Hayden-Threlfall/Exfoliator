#include "ClearCore.h"
#include <Arduino.h>

#define YAxis         ConnectorM0
#define XAxis         ConnectorM1
#define TakeUpMotor   ConnectorM2
#define SourceMotor   ConnectorM3
#define INPUT_A_FILTER 20

#define XAxisLimitMM 220
#define YAxisLimitMM 70
#define AxesPulsesPerMM 640


// DEPRICIATED EXFOLIATE DEFINITIONS //
/*
#define XAxisInitialChipwell 102.55 // 104
#define YAxisInitialChipwell 6.5// 6.25
#define ChipWellPitch 12.5

// Exfoliate Varibles and Functions
ProcessStep currentStep = IDLE;
bool robotCurrentlyExfoliating = false;
double targetChuckTemp = 30;
int columnOfWorkingChip = 0;
int rowOfWorkingChip = 0;
*/


// UNUSED ENCODER DEFINITIONS //
/*
6400 Pulses per Revolution. This is configured in Teknic motor configuration software.
1 Revolution per 10 MM. This is based on Bosch Rexroth linear rails
1/640 or 0.0015625 Pulses per MM
*/
// #define TRIGGER_PULSE_TIME 25

/*
1024 ppr encoder
16mm OD shaft
1 rev = pi * 16 mm
20.371 pulses per mm
*/
// #define EncoderPulsesPerMM 20.371

// bool swapDirection = false;
// bool indexInverted = false;
// int position = 0;
// int velocity = 0;
// int indexPosition = 0;
// int lastIndexPosition = 0;
// bool quadratureError = false;

double XPosition = 0;
double YPosition = 0;

double tapeMaxTorque = 100;
double tapeMaxSpeed = 100;

unsigned long hBridgeResetTimer = 0;
bool hBridgeResetPending = false;
unsigned long torqueDelayTimer = 0;
bool torqueDelayPending = false;
unsigned long velocityDelayTimer = 0;
bool velocityDelayPending = false;

void motorSetup() {
    MotorMgr.MotorModeSet(MotorManager::MOTOR_M0M1, Connector::CPM_MODE_STEP_AND_DIR);

    YAxis.HlfbMode(MotorDriver::HLFB_MODE_STATIC);
    YAxis.HlfbCarrier(MotorDriver::HLFB_CARRIER_482_HZ);
    YAxis.VelMax(INT32_MAX);
    YAxis.AccelMax(INT32_MAX);

    XAxis.HlfbMode(MotorDriver::HLFB_MODE_STATIC);
    XAxis.HlfbCarrier(MotorDriver::HLFB_CARRIER_482_HZ);
    XAxis.VelMax(INT32_MAX);
    XAxis.AccelMax(INT32_MAX);

    YAxis.EnableRequest(true);
    Serial.println("TakeUpMotor Enabled");

    XAxis.EnableRequest(true);
    Serial.println("SourceMotor Enabled");

    // Tension Motors Setup
    MotorMgr.MotorModeSet(MotorManager::MOTOR_M2M3, Connector::CPM_MODE_A_DIRECT_B_PWM);
    TakeUpMotor.EnableRequest(true);
    Serial.println("TakeUpMotor Enabled");

    SourceMotor.EnableRequest(true);
    Serial.println("SourceMotor Enabled");

    unsigned long startHomeTimer = 60000;
    // Waits up to 60 seconds for motors to home
    Serial.println("Waiting for motors to home...");
    unsigned long startHomeTime = millis();
    while (!checkIfAxesAreReady()) {
        delay(250);
        if (checkTimer(startHomeTime, 5000)) {
            emergencyStop();
            break;
        }
    }
}

/*
void encoderSetup() {
    // Enable the encoder input feature
    EncoderIn.Enable(true);
    // Zero the position to start
    EncoderIn.Position(0);
    // Set the encoder direction
    EncoderIn.SwapDirection(swapDirection);
    // Set the sense of index detection (true = rising edge, false = falling edge)
    EncoderIn.IndexInverted(indexInverted);
}
*/

bool checkIfAxesAreReady() {
    return (YAxis.HlfbState() == MotorDriver::HLFB_ASSERTED) &&
           (XAxis.HlfbState() == MotorDriver::HLFB_ASSERTED);
}

void checkHBridgeOverload() {
    if (StatusMgr.StatusRT().bit.HBridgeOverloaded && !hBridgeResetPending) {
        StatusMgr.HBridgeReset();
        hBridgeResetPending = true;
        hBridgeResetTimer = millis();
    }

    if (hBridgeResetPending && checkTimer(hBridgeResetTimer, 10)) {
        hBridgeResetPending = false;
    }
}

double getXPosition() {
    return XPosition;
}

void setXPosition(double updatedXPosition) {
    XPosition = updatedXPosition;
}

double getYPosition() {
    return YPosition;
}

void setYPosition(double updatedYPosition) {
    YPosition = updatedYPosition;
}

bool tapeTorque(int commandedTorque) {
    if (abs(commandedTorque) > abs(tapeMaxTorque)) {
        Serial.println("Move rejected, invalid torque requested");
        return false;
    }

    double scaleFactor = 255.0 / tapeMaxTorque;
    int dutyRequest = abs(commandedTorque) * scaleFactor;

    bool newDirection = (commandedTorque < 0);
    static bool lastDirection = false;

    // Handle direction changes
    if (newDirection != lastDirection) {
        TakeUpMotor.MotorInAState(newDirection);
        torqueDelayPending = true;
        torqueDelayTimer = millis(); // start delay
        lastDirection = newDirection;
        return false; // not ready yet
    }

    // Wait until delay passes
    if (torqueDelayPending && !checkTimer(torqueDelayTimer, (20 + INPUT_A_FILTER))) {
        return false; // still waiting
    }
    torqueDelayPending = false;

    // Safe to apply torque
    TakeUpMotor.MotorInBDuty(dutyRequest);

    Serial.print("Torque command applied: ");
    Serial.println(commandedTorque);

    return true;
}

bool tapeVelocity(double commandedVelocity) {
    if (abs(commandedVelocity) >= abs(tapeMaxSpeed)) {
        Serial.println("Move rejected, requested velocity at or over the limit.");
        return false;
    }

    double scaleFactor = 255.0 / tapeMaxSpeed;
    int dutyRequest = abs(commandedVelocity) * scaleFactor;

    bool newDirection = (commandedVelocity < 0);
    static bool lastDirection = false;

    // Handle direction changes
    if (newDirection != lastDirection) {
        SourceMotor.MotorInAState(newDirection);
        velocityDelayPending = true;
        velocityDelayTimer = millis(); // start delay
        lastDirection = newDirection;
        return false; // not ready yet
    }

    // Wait until delay passes
    if (velocityDelayPending && !checkTimer(velocityDelayTimer, (20 + INPUT_A_FILTER))) {
        return false; // still waiting
    }
    velocityDelayPending = false;

    // Safe to apply velocity
    SourceMotor.MotorInBDuty(dutyRequest);

    Serial.print("Velocity command applied: ");
    Serial.println(commandedVelocity);

    return true;
}

bool moveXandYAxes(double targetXPosition, double targetYPosition) {
    if (targetXPosition > XAxisLimitMM) {
        targetXPosition = XAxisLimitMM;
    }
    if (targetXPosition < 0) {
        targetXPosition = 0;
    }

    if (targetYPosition > YAxisLimitMM) {
        targetYPosition = YAxisLimitMM;
    }
    if (targetYPosition < 0) {
        targetYPosition = 0;
    }

    Serial.println("Motors are Ready");

    Serial.print("Commanding X Position of: ");
    Serial.print(targetXPosition);
    Serial.println(" MM");

    Serial.print("Commanding Y Position of: ");
    Serial.print(targetYPosition);
    Serial.println(" MM");

    double relativeXMovement = getXPosition() - targetXPosition;
    double relativeYMovement = getYPosition() - targetYPosition;

    // Command the move of incremental distance
    XAxis.Move(relativeXMovement * AxesPulsesPerMM);
    YAxis.Move(relativeYMovement * AxesPulsesPerMM);

    setXPosition(targetXPosition);
    setYPosition(targetYPosition);

    return true;
}

void disableXMotor() {
    XAxis.EnableRequest(false);
    Serial.println("X Motor Disabled");
}

void disableYMotor() {
    YAxis.EnableRequest(false);
    Serial.println("Y Motor Disabled");
}

void disableTakeUpMotor() {
    TakeUpMotor.EnableRequest(false);
    tapeVelocity(0);
    Serial.println("TakeUp Motor Disabled");
}

void disableSourceMotor() {
    SourceMotor.EnableRequest(false);
    tapeTorque(0);
    Serial.println("Source Motor Disabled");
}

String getMotorXStateString() {
    // Bind by reference, no copy
    const volatile MotorDriver::StatusRegMotor &status = XAxis.StatusReg();

    switch (status.bit.ReadyState) {
        case MotorDriver::MOTOR_DISABLED:
            return "Disabled";
        case MotorDriver::MOTOR_ENABLING:
            return "Enabled";
        case MotorDriver::MOTOR_READY:
            return "Ready";
        case MotorDriver::MOTOR_MOVING:
            return "Moving";
        case MotorDriver::MOTOR_FAULTED:
            return "Faulted";
        default:
            return "Unknown";
    }
}

String getMotorYStateString() {
    // Same fix here
    const volatile MotorDriver::StatusRegMotor &status = YAxis.StatusReg();

    switch (status.bit.ReadyState) {
        case MotorDriver::MOTOR_DISABLED:
            return "Disabled";
        case MotorDriver::MOTOR_ENABLING:
            return "Enabled";
        case MotorDriver::MOTOR_READY:
            return "Ready";
        case MotorDriver::MOTOR_MOVING:
            return "Moving";
        case MotorDriver::MOTOR_FAULTED:
            return "Faulted";
        default:
            return "Unknown";
    }
}