#include "ClearCore.h"
#include <SPI.h>
#include <Ethernet.h>

volatile bool eStopTriggered = false;

// Static network configuration
#define baudRate 9600

#define SERVER_PORT 1053
byte mac[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED};
IPAddress ip(192, 168, 3, 100);           // Arduino IP
IPAddress serverIp(192, 168, 3, 120);     // Python server IP

EthernetClient client;
char incomingData[300]; // Buffer for receiving commands
char outgoingJson[512]; // Buffer for sending JSON
char buffer[100];

double exfoliationStep = 0;
unsigned long lastJsonSend = 0;
const unsigned long JSON_SEND_INTERVAL = 1000; // Send JSON every 1 second

void setup() {
    Serial.begin(baudRate);

    // Make sure the physical link is active before continuing
    while (Ethernet.linkStatus() == LinkOFF) {
      Serial.println("The Ethernet cable is unplugged...");
      delay(1000);
    }

    // Start Ethernet with static IP
    Ethernet.begin(mac, ip);
    Serial.print("Assigned static IP: ");
    Serial.println(Ethernet.localIP());

    connectToServer();

    // Motors Setup
    motorSetup();

    // Solenoid Setup
    pnuematicSetup();

    // Thermistor Setup
    thermistorSetup();
    
    // Heater Setup
    heaterSetup();
}

void loop() {
    if (eStopTriggered) {
        emergencyStop();
        // Send emergency stop status in JSON
        sendStatusJson();
        
        while (true) {
            Serial.println("EMERGENCY STOPPED. Reset required.");
            delay(1000); // Wait indefinitely
        }
    }

    static unsigned long lastConnectionAttempt = 0;

    // Try to reconnect if not connected
    if (!client.connected() && checkTimer(lastConnectionAttempt, 5000)) {
        connectToServer();
    }

    // Read incoming commands
    if (client.connected() && client.available()) {
        size_t len = client.readBytesUntil('\n', incomingData, sizeof(incomingData) - 1);
        incomingData[len] = '\0'; // Null-terminate the string
        String cmd = String(incomingData);
        cmd.trim(); // Remove leading/trailing whitespace

        Serial.print("Received command: ");
        Serial.println(cmd);

        // Process the command
        processCommand(cmd);
    }

    // Send JSON status periodically
    if (checkTimer(lastJsonSend, JSON_SEND_INTERVAL)) {
        sendStatusJson();
    }

    // Run heater control
    heaterStep();

    delay(25);
}

void processCommand(String cmd) {
    // Movement commands
    if (cmd.startsWith("MoveX ")) {
        float position = cmd.substring(6).toFloat();
        Serial.print("Moving X to position: ");
        Serial.println(position);
        moveXandYAxes(position, getYPosition());
        client.println("OK");
    }
    else if (cmd.startsWith("MoveY ")) {
        float position = cmd.substring(6).toFloat();
        Serial.print("Moving Y to position: ");
        Serial.println(position);
        moveXandYAxes(getXPosition(), position);
        client.println("OK");
    }
    
    // Homing commands
    else if (cmd == "Home") {
        Serial.println("Homing all axes");
        // Implement home all functionality
        client.println("Homing all axes");
    }
    else if (cmd == "HomeX") {
        Serial.println("Homing X axis");
        enableXMotor();
        client.println("Homing X axis");
    }
    else if (cmd == "HomeY") {
        Serial.println("Homing Y axis");
        enableYMotor();
        client.println("Homing Y axis");
    }
    
    // Motor disable commands
    else if (cmd == "DisableX") {
        disableXMotor();
        client.println("X Motor Disabled");
    }
    else if (cmd == "DisableY") {
        disableYMotor();
        client.println("Y Motor Disabled");
    }
    
    // Pneumatic commands
    else if (cmd == "ExtendNozzle") {
        lowerNozzle();
        client.println("Nozzle Extended");
    }
    else if (cmd == "RetractNozzle") {
        raiseNozzle();
        client.println("Nozzle Retracted");
    }
    else if (cmd == "ExtendChipStage") {
        extendStage();
        client.println("Chip Stage Extended");
    }
    else if (cmd == "RetractChipStage") {
        retractStage();
        client.println("Chip Stage Retracted");
    }
    else if (cmd == "ExtendStamp") {
        raiseStamp();
        client.println("Stamp Extended");
    }
    else if (cmd == "RetractStamp") {
        lowerStamp();
        client.println("Stamp Retracted");
    }
    
    // Vacuum commands
    else if (cmd == "VacNozzleOn") {
        activateNozzleVacuum();
        client.println("Nozzle Vacuum On");
    }
    else if (cmd == "VacNozzleOff") {
        disableNozzleVacuum();
        client.println("Nozzle Vacuum Off");
    }
    else if (cmd == "ChuckOn") {
        activateChuckVacuum();
        client.println("Chuck Vacuum On");
    }
    else if (cmd == "ChuckOff") {
        disableChuckVacuum();
        client.println("Chuck Vacuum Off");
    }
    
    // Temperature command
    else if (cmd.startsWith("SetTemperature ")) {
        float temp = cmd.substring(15).toFloat();
        Serial.print("Setting temperature to: ");
        Serial.println(temp);
        setTargetTemperature(temp);
        client.println("Temperature set");
    }
    
    // Tape motor command
    else if (cmd.startsWith("Tape ")) {
        // Parse: Tape {speed} {torque} {time}
        int firstSpace = cmd.indexOf(' ', 5);
        int secondSpace = cmd.indexOf(' ', firstSpace + 1);
        
        if (firstSpace > 0 && secondSpace > 0) {
            int speed = cmd.substring(5, firstSpace).toInt();
            int torque = cmd.substring(firstSpace + 1, secondSpace).toInt();
            int duration = cmd.substring(secondSpace + 1).toInt();
            
            Serial.print("Tape motor - Speed: ");
            Serial.print(speed);
            Serial.print(", Torque: ");
            Serial.print(torque);
            Serial.print(", Duration: ");
            Serial.println(duration);
            
            // Run tape motor for specified duration
            unsigned long startTime = millis();
            tapeVelocity(speed);
            tapeTorque(torque);
            
            while (millis() - startTime < duration && !eStopTriggered) {
                delay(10);
            }
            
            // Stop tape motor
            tapeVelocity(0);
            tapeTorque(0);
            
            client.println("Tape motor operation complete");
        }
    }
    
    // Emergency stop
    else if (cmd == "STOP") {
        Serial.println("Emergency stop commanded");
        emergencyStop();
        client.println("EMERGENCY STOP ACTIVATED");
    }
    
    // Unknown command
    else {
        Serial.print("Unknown command: ");
        Serial.println(cmd);
        client.println("Unknown command");
    }
}

void sendStatusJson() {
    if (!client.connected()) {
        return;
    }
    
    // Get motor states
    String stateX = getMotorXStateString();
    String stateY = getMotorYStateString();
    
    // Get pneumatic states
    bool nozzleState = getNozzleExtended();
    bool stageState = getStageExtended();
    bool stampState = getStampExtended();
    
    // Get vacuum states
    bool vacNozzleState = getNozzleVacuum();
    bool chuckState = getChuckVacuum();
    
    // Get tape motor states (for now, return current commanded values)
    // In a real implementation, you might track these values
    int tapeSpeed = 0;  // You'd track this from tape commands
    int tapeTorque = 0; // You'd track this from tape commands
    
    // Get temperature values
    float currentTemp = getThermistor();
    float setTemp = getTargetTemperature();
    
    // Build JSON string
    snprintf(outgoingJson, sizeof(outgoingJson),
        "{"
        "\"x\":%.2f,"
        "\"y\":%.2f,"
        "\"stateX\":\"%s\","
        "\"stateY\":\"%s\","
        "\"tape\":[%d,%d],"
        "\"nozzle\":%s,"
        "\"stage\":%s,"
        "\"stamp\":%s,"
        "\"vacnozzle\":%s,"
        "\"chuck\":%s,"
        "\"settemp\":%.2f,"
        "\"temp\":%.2f,"
        "\"eStopTriggered\":%s"
        "}",
        getXPosition(),
        getYPosition(),
        stateX.c_str(),
        stateY.c_str(),
        tapeSpeed,
        tapeTorque,
        nozzleState ? "true" : "false",
        stageState ? "true" : "false",
        stampState ? "true" : "false",
        vacNozzleState ? "true" : "false",
        chuckState ? "true" : "false",
        setTemp,
        currentTemp,
        eStopTriggered ? "true" : "false"
    );
    
    // Send JSON
    client.println(outgoingJson);
    
    Serial.print("Sent JSON: ");
    Serial.println(outgoingJson);
}

bool checkTimer(unsigned long &lastTime, unsigned long duration) {
    if (millis() - lastTime >= duration) {
        lastTime = millis();
        return true;
    }
    return false;
}

bool connectToServer() {
    if (client.connected()) {
        return true;
    }
    
    client.stop();
    Serial.println("Connecting to server...");
    
    if (client.connect(serverIp, SERVER_PORT)) {
        Serial.println("Connected to server!");
        return true;
    } else {
        Serial.println("Connection failed. Will retry...");
        return false;
    }
}

void emergencyStop() {
    eStopTriggered = true;
    disableXMotor();
    disableYMotor();
    disableTakeUpMotor();
    disableSourceMotor();
    heaterOff();
}