bool nozzleExtended = false;
bool nozzleVacuum = false;
bool chuckVacuum = false;
bool stageRetracted = false;
bool stampExtended = false;


void pnuematicSetup() {
    pinMode(IO0, OUTPUT);
    pinMode(IO1, OUTPUT);
    pinMode(IO2, OUTPUT);
    pinMode(IO3, OUTPUT);
    pinMode(IO4, OUTPUT);

    disableNozzleVacuum();
    raiseNozzle();
    raiseStamp();
    disableChuckVacuum();
    extendStage();
}

bool getNozzleExtended() {
  return nozzleExtended;
}
bool getNozzleVacuum() {
  return nozzleVacuum;
}
bool getChuckVacuum () {
  return chuckVacuum;
}
bool getStageRetracted() {
  return stageRetracted;
}
bool getStampExtended() {
  return stampExtended;
}

void lowerNozzle() {
    digitalWrite(IO0, true);
    nozzleExtended = true;
}

void raiseNozzle() {
    digitalWrite(IO0, false);
    nozzleExtended = false;
}

void retractStage() {
    digitalWrite(IO2, true);
    stageRetracted = false;
}

void extendStage() {
    digitalWrite(IO2, false);
    stageRetracted = true;
}

void raiseStamp() {
    digitalWrite(IO3, false);
    stampExtended = false;
}

void lowerStamp() {
    digitalWrite(IO3, true);
    stampExtended = true;

}

void activateChuckVacuum() {
    digitalWrite(IO4, true);
    chuckVacuum = true;
}

void disableChuckVacuum() {
    digitalWrite(IO4, false);
    chuckVacuum = false;
}

void activateNozzleVacuum() {
    digitalWrite(IO1, true);
    nozzleVacuum = true;
}

void disableNozzleVacuum() {
    digitalWrite(IO1, false);
    nozzleVacuum = false;
}