let socket;
let tempChart;
let isConnected = false;
let currentTemp = 0;
let targetTemp = 0;
let position = { x: 0, y: 0 };
let motorStates = { x: 'MOTOR_DISABLED', y: 'MOTOR_DISABLED' };
let pneumatics = { nozzle: false, stage: false, stamp: false };
let vacuums = { vacnozzle: false, chuck: false };
let tape = { speed: 0, torque: 0 };
let tempData = [];
let selectedChips = [];
let eStopTriggered = false;
let currentEditingMacro = null;
let macrosList = [];

document.addEventListener('DOMContentLoaded', function() {
    initializeSocket();
    initializeChart();
    const chipsContainer = document.querySelector('.chips');
    if (chipsContainer) {
        chipsContainer.addEventListener('click', handleChipSelection);
    }
    updatePneumaticsDisplay();
    updateVacuumsDisplay();
    loadMacroList();

});

function initializeSocket() {
    socket = io();
    
    socket.on('connect', function() {
        updateConnectionStatus(false);
        addLog('Connected to web server');
        socket.emit('get_arduino_status');
    });

    socket.on('arduino_connection_status', function(data) {
        updateConnectionStatus(data.connected);
        addLog(data.connected ? 'Arduino connected' : 'Arduino disconnected');
    });
    
    socket.on('disconnect', function() {
        updateConnectionStatus(false);
        addLog('Disconnected from server');
    });
    
    socket.on('connection_status', function(data) {
        updateConnectionStatus(data.connected);
    });
    
    socket.on('temperature_update', function(data) {
        currentTemp = data.temperature || 0;
        targetTemp = data.set_temperature || 0;
        updateTemperatureDisplay();
        updateTempChart();
    });
    
    socket.on('position_update', function(data) {
        position = data;
        updatePositionDisplay();
    });
    
    socket.on('motor_states_update', function(data) {
        motorStates = data;
        updateMotorStatesDisplay();
    });
    
    socket.on('pneumatics_update', function(data) {
        pneumatics = data;
        updatePneumaticsDisplay();
    });
    
    socket.on('vacuums_update', function(data) {
        vacuums = data;
        updateVacuumsDisplay();
    });
    
    socket.on('tape_update', function(data) {
        tape = data;
        updateTapeDisplay();
    });
    
    socket.on('estop_update', function(data) {
        eStopTriggered = data.triggered;
        updateEmergencyStopDisplay();
    });
    
    socket.on('command_sent', function(data) {
        addLog(`Sent: ${data.command}`);
    });
    
    socket.on('machine_response', function(data) {
        addLog(`Response: ${data.response}`);
    });

    socket.on('macro_list', function(data) {
        macrosList = data.macros || [];
        //adding macro list to chip selector options

        if (macrosList.length === 0) {
        const option = document.createElement("option");
        option.textContent = "No Saved Macros";
        option.value = ""; // empty value
        document.querySelector("#action").appendChild(option);
        } else {
            const select = document.querySelector("#action");
            select.innerHTML = ''; // clear existing options

            macrosList.forEach(macro => {
                const option = document.createElement("option");
                option.textContent = macro;  // text shown in dropdown
                option.value = macro;        // value submitted
                select.appendChild(option);
            });
        }
        updateMacroList();
    });
    
    socket.on('macro_created', function(data) {
        addLog(`Macro created: ${data.name}`);
        loadMacroList();
    });
    
    socket.on('macro_deleted', function(data) {
        addLog(`Macro deleted: ${data.name}`);
        loadMacroList();
    });
    
    socket.on('macro_executed', function(data) {
        addLog(`Executing macro: ${data.name}`);
    });
    
    socket.on('macro_error', function(data) {
        addLog(`Macro error: ${data.error}`);
    });
}

function initializeChart() {
    const ctx = document.getElementById('tempChart').getContext('2d');
    tempChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Current Temp',
                    data: [],
                    borderColor: '#EF4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    tension: 0.1
                },
                {
                    label: 'Target Temp',
                    data: [],
                    borderColor: '#F59E0B',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    borderDash: [5, 5],
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: 'white' }
                }
            },
            scales: {
                x: {
                    ticks: { color: 'white' },
                    grid: { color: '#374151' }
                },
                y: {
                    ticks: { color: 'white' },
                    grid: { color: '#374151' }
                }
            }
        }
    });
}

function updateConnectionStatus(connected) {
    isConnected = connected;
    const status = document.getElementById('connectionStatus');
    status.className = `status ${connected ? 'connected' : 'disconnected'}`;
    status.querySelector('span').textContent = connected ? 'Connected' : 'Disconnected';
}

function updateTemperatureDisplay() {
    document.getElementById('currentTemp').textContent = `${currentTemp}°C`;
    document.getElementById('targetTemp').textContent = `${targetTemp}°C`;
}

function updatePositionDisplay() {
    document.getElementById('posX').textContent = `${position.x} mm`;
    document.getElementById('posY').textContent = `${position.y} mm`;
}

function updateMotorStatesDisplay() {
    const stateClasses = {
        'MOTOR_DISABLED': 'state-disabled',
        'MOTOR_ENABLING': 'state-enabling', 
        'MOTOR_FAULTED': 'state-faulted',
        'MOTOR_READY': 'state-ready',
        'MOTOR_MOVING': 'state-moving'
    };
    
    Object.keys(motorStates).forEach(axis => {
        const stateEl = document.getElementById(`motorState${axis.toUpperCase()}`);
        if (stateEl) {
            const state = motorStates[axis];
            stateEl.textContent = state;
            stateEl.className = `motor-state ${stateClasses[state] || 'state-disabled'}`;
        }
    });
}

function updatePneumaticsDisplay() {
    Object.keys(pneumatics).forEach(component => {
        const statusEl = document.getElementById(component + 'Status');
        if (statusEl) {
            statusEl.className = `status-indicator ${pneumatics[component] ? 'active' : ''}`;
        }
    });
}

function updateVacuumsDisplay() {
    Object.keys(vacuums).forEach(component => {
        const statusEl = document.getElementById(component + 'Status');
        if (statusEl) {
            statusEl.className = `status-indicator ${vacuums[component] ? 'active' : ''}`;
        }
    });
}

function updateTapeDisplay() {
    document.getElementById('currentTapeSpeed').textContent = tape.speed || 0;
    document.getElementById('currentTapeTorque').textContent = tape.torque || 0;
    if (document.activeElement.id !== 'tapeSpeed') {
        document.getElementById('tapeSpeed').value = tape.speed || 0;
    }
    if (document.activeElement.id !== 'tapeTorque') {
        document.getElementById('tapeTorque').value = tape.torque || 0;
    }
}

function updateEmergencyStopDisplay() {
    const emergencyButton = document.getElementById('emergencyButton');
    const restartMessage = document.getElementById('restartMessage');
    if (eStopTriggered) {
        emergencyButton.classList.add('estop-active');
        restartMessage.style.display = 'block';
    } else {
        emergencyButton.classList.remove('estop-active');
        restartMessage.style.display = 'none';
    }
}

function updateTempChart() {
    const now = new Date().toLocaleTimeString();
    if (tempChart.data.labels.length >= 20) {
        tempChart.data.labels.shift();
        tempChart.data.datasets[0].data.shift();
        tempChart.data.datasets[1].data.shift();
    }
    tempChart.data.labels.push(now);
    tempChart.data.datasets[0].data.push(currentTemp);
    tempChart.data.datasets[1].data.push(targetTemp);
    tempChart.update('none');
}

function addLog(message) {
    const console = document.getElementById('console');
    const timestamp = new Date().toLocaleTimeString();
    const logLine = document.createElement('div');
    logLine.className = 'console-line';
    logLine.textContent = `[${timestamp}] ${message}`;
    console.appendChild(logLine);
    console.scrollTop = console.scrollHeight;
    while (console.children.length > 10) {
        console.removeChild(console.firstChild);
    }
}

function loadMacroList() {
    socket.emit('get_macros');
}

function updateMacroList() {
    const listContainer = document.getElementById('macroList');
    if (macrosList.length === 0) {
        listContainer.innerHTML = '<div style="color: #6B7280; text-align: center; padding: 20px;">No macros saved yet</div>';
        return;
    }
    listContainer.innerHTML = '';
    macrosList.forEach(macro => {
        const macroItem = document.createElement('div');
        macroItem.className = 'macro-item';
        macroItem.innerHTML = `
            <span class="macro-name">${macro}</span>
            <div class="macro-actions">
                <button class="button btn-success" onclick="runMacro('${macro}')">Run</button>
                <button class="button btn-warning" onclick="editMacro('${macro}')">Edit</button>
                <button class="button btn-danger" onclick="deleteMacro('${macro}')">Delete</button>
            </div>
        `;
        listContainer.appendChild(macroItem);
    });
}

function createNewMacro() {
    const name = document.getElementById('newMacroName').value.trim();
    if (!name) {
        addLog('Please enter a macro name');
        return;
    }
    currentEditingMacro = name;
    document.getElementById('editingMacroName').textContent = name;
    document.getElementById('macroContent').value = getMacroTemplate();
    openMacroEditor();
}

function getMacroTemplate() {
    return `# Macro: ${currentEditingMacro}
# Created: ${new Date().toLocaleString()}
# 
# Available Commands:
# - MoveX <position> or MoveX CHIP_X
# - MoveY <position> or MoveY CHIP_Y
# - EnableX / EnableY
# - DisableX / DisableY
# - ExtendNozzle / RetractNozzle
# - ExtendChipStage / RetractChipStage
# - ExtendStamp / RetractStamp
# - VacNozzleOn / VacNozzleOff
# - ChuckOn / ChuckOff
# - SetTemperature <temp>
# - Tape <speed> <torque> <time_ms>
# - StopTape
# - delay <milliseconds>
# - STOP (emergency stop)
#
# Variables:
# - CHIP_X, CHIP_Y, STAGE_X can be used in place of numeric values
#
# Example sequence:
# EnableX
# EnableY
# delay 500
# MoveX CHIP_X
# MoveY CHIP_Y
# delay 1000
# ExtendNozzle
# delay 500
# VacNozzleOn
# delay 1000
# RetractNozzle

# Your macro commands below:
`;
}

function openMacroEditor() {
    document.getElementById('overlay').classList.add('active');
    document.getElementById('macroEditor').classList.add('active');
}

function closeMacroEditor() {
    document.getElementById('overlay').classList.remove('active');
    document.getElementById('macroEditor').classList.remove('active');
    currentEditingMacro = null;
}

function saveMacro() {
    if (!currentEditingMacro) return;
    const content = document.getElementById('macroContent').value;
    const variables = {
        CHIP_X: parseFloat(document.getElementById('CHIP_X').value),
        CHIP_Y: parseFloat(document.getElementById('CHIP_Y').value),
        STAGE_X: parseFloat(document.getElementById('STAGE_X').value)
    };
    socket.emit('save_macro', {
        name: currentEditingMacro,
        content: content,
        variables: variables
    });
    closeMacroEditor();
    document.getElementById('newMacroName').value = '';
}

function editMacro(name) {
    currentEditingMacro = name;
    document.getElementById('editingMacroName').textContent = name;
    socket.emit('load_macro', { name: name });
    socket.once('macro_content', function(data) {
        document.getElementById('macroContent').value = data.content || getMacroTemplate();
        openMacroEditor();
    });
}

function runMacro(name) {
    const variables = {
        CHIP_X: parseFloat(document.getElementById('CHIP_X').value),
        CHIP_Y: parseFloat(document.getElementById('CHIP_Y').value),
        STAGE_X: parseFloat(document.getElementById('STAGE_X').value)
    };
    socket.emit('run_macro', {
        name: name,
        variables: variables
    });
}


function runChipMacro(name,x,y) {
    const variables = {
        CHIP_X: x,
        CHIP_Y: y,
        STAGE_X: parseFloat(document.getElementById('STAGE_X').value)
    };
    socket.emit('run_macro', {
        name: name,
        variables: variables
    });
}

function deleteMacro(name) {
    if (confirm(`Are you sure you want to delete macro "${name}"?`)) {
        socket.emit('delete_macro', { name: name });
    }
}

function homeAxis(axis) {
    socket.emit('home_axis', { axis: axis });
}

function enableAxis(axis) {
    socket.emit('enable_axis', { axis: axis });
}

function disableMotor(axis) {
    socket.emit('disable_motor', { axis: axis });
}

function moveToPosition(axis) {
    const inputId = axis.toLowerCase() + 'PositionInput';
    const position = parseFloat(document.getElementById(inputId).value);
    socket.emit('move_position', { axis: axis, position: position });
}

function controlPneumatic(component, action) {
    socket.emit('pneumatic_control', { component: component, action: action });
}

function controlVacuum(component, action) {
    socket.emit('vacuum_control', { component: component, action: action });
}

function setTemperature() {
    const temp = parseInt(document.getElementById('tempInput').value);
    socket.emit('set_temperature', { temperature: temp });
}

function emergencyStop() {
    socket.emit('emergency_stop');
}

function runTapeMotor() {
    const speed = parseInt(document.getElementById('tapeSpeed').value);
    const torque = parseInt(document.getElementById('tapeTorque').value);
    const time = parseInt(document.getElementById('tapeTime').value);
    socket.emit('tape_motor', { speed: speed, torque: torque, time: time });
}

function stopTapeMotor() {
    socket.emit('send_command', { command: 'StopTape' });
}

function sendCustomCommand() {
    const command = document.getElementById('customCommand').value;
    if (command.trim()) {
        socket.emit('send_command', { command: command });
        document.getElementById('customCommand').value = '';
    }
}

document.getElementById('customCommand').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') sendCustomCommand();
});

[
    ['xPositionInput', () => moveToPosition('X')],
    ['yPositionInput', () => moveToPosition('Y')],
    ['tempInput', setTemperature],
    ['tapeSpeed', runTapeMotor],
    ['tapeTorque', runTapeMotor],
    ['tapeTime', runTapeMotor],
    ['newMacroName', createNewMacro]
].forEach(([id, fn]) => {
    document.getElementById(id).addEventListener('keypress', e => e.key === 'Enter' && fn());
});

function handleChipSelection(event) {
    const button = event.target;
    if (button.tagName === 'BUTTON' && button.classList.contains('chip')) {
        const chipId = button.id;
        if (button.classList.contains('selected')) {
            button.classList.remove('selected');
            const index = selectedChips.indexOf(chipId);
            if (index !== -1) {
                selectedChips.splice(index, 1);
            }
        } else {
            button.classList.add('selected');
            selectedChips.push(chipId);
        }
    }
}

function clearChips() {
    selectedChips = [];
    document.querySelectorAll('.chip.selected').forEach(button => {
        button.classList.remove('selected');
    });
}

function submitChips() {
    selectedChips.sort();

    const rows = {"A": 1,"B": 2, "C":3, "D":4, "E":5, "F":6 }

    const actionSelect = document.querySelector('#action').value;

    for (chip of selectedChips){
        let xcor = 105.5  + (chip[1])*12.5 //i forgor distance between each chip
        let ycor = 4.5 + rows[chip[0]]*12.5 //init values hardcode for now cuzi. dont have macro variables on this branch
        runChipMacro(actionSelect,xcor,ycor);


    }   
}

