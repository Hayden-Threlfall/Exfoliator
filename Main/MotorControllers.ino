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

double XPosition = 0;
double YPosition = 0;

double tapeMaxTorque = 100;
double tapeMaxSpeed = 100;

// Tape motor state tracking
int currentTapeSpeed = 0;
int currentTapeTorque = 0;
unsigned long tapeOperationStartTime = 0;
unsigned long tapeOperationDuration = 0;
bool tapeOperationActive = false;

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
    Serial.println("Y Motor Enabled");

    XAxis.EnableRequest(true);
    Serial.println("X Motor Enabled");

    // Tension Motors Setup
    MotorMgr.MotorModeSet(MotorManager::MOTOR_M2M3, Connector::CPM_MODE_A_DIRECT_B_PWM);
    TakeUpMotor.EnableRequest(true);
    Serial.println("TakeUpMotor Enabled");

    SourceMotor.EnableRequest(true);
    Serial.println("SourceMotor Enabled");

    // Wait for motors to home (with timeout)
    Serial.println("Waiting for motors to home...");
    unsigned long startHomeTime = millis();
    while (!checkIfAxesAreReady()) {
        delay(250);
        if (millis() - startHomeTime > 60000) { // 60 second timeout
            Serial.println("Motor homing timeout!");
            emergencyStop();
            break;
        }
    }
    
    Serial.println("Motor setup complete");
}

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
        torqueDelayTimer = millis();
        lastDirection = newDirection;
        return false;
    }

    // Wait until delay passes
    if (torqueDelayPending && !checkTimer(torqueDelayTimer, (20 + INPUT_A_FILTER))) {
        return false;
    }
    torqueDelayPending = false;

    // Apply torque
    TakeUpMotor.MotorInBDuty(dutyRequest);
    currentTapeTorque = commandedTorque; // Track current torque

    Serial.print("Torque command applied: ");
    Serial.println(commandedTorque);

    return true;
}

bool tapeVelocity(double commandedVelocity) {
    if (abs(commandedVelocity) > abs(tapeMaxSpeed)) {
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
        velocityDelayTimer = millis();
        lastDirection = newDirection;
        return false;
    }

    // Wait until delay passes
    if (velocityDelayPending && !checkTimer(velocityDelayTimer, (20 + INPUT_A_FILTER))) {
        return false;
    }
    velocityDelayPending = false;

    // Apply velocity
    SourceMotor.MotorInBDuty(dutyRequest);
    currentTapeSpeed = commandedVelocity; // Track current speed

    Serial.print("Velocity command applied: ");
    Serial.println(commandedVelocity);

    return true;
}

void startTapeOperation(int speed, int torque, unsigned long duration) {
    Serial.print("Starting tape operation - Speed: ");
    Serial.print(speed);
    Serial.print(", Torque: ");
    Serial.print(torque);
    Serial.print(", Duration: ");
    Serial.println(duration);

    // Apply the commands
    tapeVelocity(speed);
    tapeTorque(torque);
    
    // Set up timing
    tapeOperationStartTime = millis();
    tapeOperationDuration = duration;
    tapeOperationActive = true;
}

void stopTapeOperation() {
    Serial.println("Stopping tape operation");
    tapeVelocity(0);
    tapeTorque(0);
    tapeOperationActive = false;
    currentTapeSpeed = 0;
    currentTapeTorque = 0;
}

void tapeMotorStep() {
    // Check if we have an active tape operation that should be stopped
    if (tapeOperationActive) {
        if (millis() - tapeOperationStartTime >= tapeOperationDuration) {
            stopTapeOperation();
        }
    }
    
    // Handle any pending direction changes
    checkHBridgeOverload();
}

int getCurrentTapeSpeed() {
    return currentTapeSpeed;
}

int getCurrentTapeTorque() {
    return currentTapeTorque;
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

void enableXMotor() {
    XAxis.EnableRequest(true);
    Serial.println("X Motor Enabled");
}

void disableYMotor() {
    YAxis.EnableRequest(false);
    Serial.println("Y Motor Disabled");
}

void enableYMotor() {
    YAxis.EnableRequest(true);
    Serial.println("Y Motor Enabled");
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