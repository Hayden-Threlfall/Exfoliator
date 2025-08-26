#include "ClearCore.h"
#include "GlobalVars.h"
#include <SPI.h>
#include <Ethernet.h>

volatile bool eStopTriggered = false;

// Static network configuration
#define baudRate 9600

#define PORT_NUM 8888
byte mac[] = {0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED};
IPAddress ip(192, 168, 3, 100);           // Arduino IP
IPAddress serverIp(192, 168, 3, 120);     // Python server IP

EthernetClient client;
char incomingData[300]; // Buffer for receiving commands

char buffer[100];

double exfoliationStep = 0;

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

    clientConnect();

    // Motors Setup
    motorSetup();

    // Encoder Setup
    //encoderSetup();

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
        Serial.println("EMERGENCY STOP!");
        while (true) {
            // SEND json ESTOPED
            delay(1000); // Wait indefinitely
        }
    }

    static unsigned long lastAttempt = 0;

    //Reconnect if not connected
    if (checkTimer(lastAttempt, 2000)) {
        clientConnect();
    }

    // Read incoming data
    if (client.available()) {
      size_t len = client.readBytesUntil('\n', incomingData, sizeof(incomingData) - 1);
      incomingData[len] = '\0'; // Null-terminate the string
      String cmd = String(incomingData);
      cmd.trim(); // Remove leading/trailing whitespace

      Serial.print("Received command: ");
      Serial.println(cmd);

      // === Command handling ===
      if (cmd == "START") {
        // Simulate starting something
        Serial.println("Action: START");
        exfoliateStart();
        client.println("Started");
      }
      else if (cmd == "STOP") {
        Serial.println("Action: STOP");
        exfoliateStop();
        client.println("Stopped");
      }
      else if (cmd == "ping") {
        client.println("pong");
      }
      else {
        Serial.print("Unknown command: ");
        Serial.println(cmd);
        client.println("Unknown command");
      }
    }

    exfoliateStep();

    heaterStep();
    //znPIDTunerStep();

    delay(25);
}

unsigned long lastTime = 0;

double lastPosition = 0;

void zeroEncoder() {
  
  lastPosition = EncoderIn.Position();

}

bool checkEncoder(double targetDistance) {

  if ( (EncoderIn.Position() * EncoderPulsesPerMM - lastPosition) <= targetDistance ) {

      return true;

    } else {

      return false;

    }

}

bool checkTimer(unsigned long &lastTime, unsigned long duration) {

    if (millis() - lastTime >= duration) {
        lastTime = millis();
        return true;
    }
    return false;
}

bool clientConnect() {
    if (!client.connected()) {
          client.stop();
          Serial.println("Connecting to server...");
          if (client.connect(serverIp, PORT_NUM)) {
            Serial.println("Connected to server!");
          } else {
            Serial.println("Connection failed. Retrying...");
            return false;
          }
        }
    return true;
}

void emergencyStop() {
    eStopTriggered = true;
    XAxis.MotorStop();
    YAxis.MotorStop();
    TakeUpMotor.MotorInBDuty(0);
    SourceMotor.MotorInBDuty(0);
    heaterOff();
}