bool nozzleExtended = false;
bool nozzleVacuum = false;
bool chuckVacuum = false;
bool stageExtended = true;
bool stampExtended = false;


void pnuematicSetup() {
    pinMode(IO0, OUTPUT);
    pinMode(IO1, OUTPUT);
    pinMode(IO2, OUTPUT);
    pinMode(IO3, OUTPUT);
    pinMode(IO4, OUTPUT);

    DisableNozzleVacuum();
    RaiseNozzle();
    RaiseStamp();
    DisableChuckVacuum();
    ExtendStage();
}

void LowerNozzle(){
    digitalWrite(IO0, true);
    nozzleExtended = false;
}

void RaiseNozzle(){
    digitalWrite(IO0, false);
    nozzleExtended = true;
}

void ExtendStage(){
    digitalWrite(IO2, false);
    stageExtended = true;
}

void RetractStage(){
    digitalWrite(IO2, true);
    stageExtended = false;
}

void RaiseStamp(){
    digitalWrite(IO3, false);
    stampExtended = false;
}

void LowerStamp(){
    digitalWrite(IO3, true);
    stampExtended = true;

}

void ActivateChuckVacuum(){
    digitalWrite(IO4, true);
    chuckVacuum = true;
}

void DisableChuckVacuum(){
    digitalWrite(IO4, false);
    chuckVacuum = false;
}

void ActivateNozzleVacuum(){
    digitalWrite(IO1, true);
    nozzleVacuum = true;
}

void DisableNozzleVacuum(){
    digitalWrite(IO1, false);
    nozzleVacuum = false;
}