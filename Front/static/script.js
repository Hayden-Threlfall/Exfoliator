let ws;
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
let commandHistory = [];
let historyIndex = -1;
let macroQueue = [];
let isMacroQueueRunning = false;
let cachedQueue = [];
let macroPaused = false;
let macros = [];


//selector states
let macroQueueStates = {'macroQueueRunning': false, 'paused': false};

//single macro states

let macroStates = {'macro': '', 'macroRunning': false, 'paused': false};

// Macro variables - now pulled from backend
let macroVariables = {
    CHIP_X: 105.0,
    CHIP_Y: 64.65,
    STAGE_X: 8.0
};

document.addEventListener('DOMContentLoaded', function() {
    initializeWebSocket();
    initializeChart();
    const chipsContainer = document.querySelector('.chips');
    if (chipsContainer) {
        chipsContainer.addEventListener('click', handleChipSelection);
    }

    const rows = document.querySelectorAll('.row-label');

    if (chipsContainer) {
        rows.forEach(row => {
            row.addEventListener('click', selectRow);
        });
    }
    
    const grid = document.querySelector('.grid');


    if (grid){
        const dropdowns = document.querySelectorAll('.dropdown');

        dropdowns.forEach(dropdown =>{
        dropdown.addEventListener('click', dropdownClick)
    })

    }

    const columns = document.querySelectorAll('.column-label');

    if (chipsContainer) {
    columns.forEach(column => {
        column.addEventListener('click', selectColumn);
    });
    }

    const selectAll = document.querySelector('#select-all')
    if (selectAll) {
        selectAll.addEventListener('click', selectAllChips);
    }



    const xToggle = document.getElementById("motorToggleX");
    const yToggle = document.getElementById("motorToggleY");

    let motorYConfirmed = false;

    yToggle.addEventListener("change", function() {
        // CHECK: Prevent enabling if nozzle is extended
        if (yToggle.checked && pneumatics.nozzle) {
            addLog('Cannot enable Y motor while nozzle is extended');
            yToggle.checked = false;
            return;
        }
        
        yToggle.checked = !yToggle.checked;

        if (!yToggle.checked) {
            enableAxis("Y");
        } else {
            disableMotor("Y");
        }

    });

    // Track last confirmed state from backend
    let motorXConfirmed = false;

    // When user tries to change state
    xToggle.addEventListener("change", function() {
        // CHECK: Prevent enabling if nozzle is extended
        if (xToggle.checked && pneumatics.nozzle) {
            addLog('Cannot enable X motor while nozzle is extended');
            xToggle.checked = false;
            return;
        }
        xToggle.checked = !xToggle.checked;


        if (!xToggle.checked) {
            enableAxis("X");
        } else {
            disableMotor("X");
        }


    });

    // New: Pneumatic and Vacuum Toggles
    setupPneumaticToggle('nozzle', 'toggleNozzle');
    setupPneumaticToggle('stage', 'toggleStage');
    setupPneumaticToggle('stamp', 'toggleStamp');
    setupVacuumToggle('vacnozzle', 'toggleVacnozzle');
    setupVacuumToggle('chuck', 'toggleChuck');

    // New function to setup pneumatic toggles
    function setupPneumaticToggle(component, toggleId) {
        const toggle = document.getElementById(toggleId);
        if (!toggle) return;

        toggle.addEventListener('change', function(e) {
            toggle.checked = pneumatics[component];
            const desiredState = component != 'stamp' ? !pneumatics[component] : pneumatics[component];
            controlPneumatic(component, desiredState ? 'extend' : 'retract');
        });
    }

    // New function to setup vacuum toggles
    function setupVacuumToggle(component, toggleId) {
        const toggle = document.getElementById(toggleId);
        if (!toggle) return;

        toggle.addEventListener('change', function(e) {
            toggle.checked = vacuums[component];
            const desiredState = !vacuums[component];
            controlVacuum(component, desiredState ? 'on' : 'off');
        });
    }



    updatePneumaticsDisplay();
    updateVacuumsDisplay();
    loadMacroList();

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

    // Special handling for custom command with history
    document.getElementById('customCommand').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            sendCustomCommand();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault(); // Prevent cursor movement
            if (commandHistory.length > 0 && historyIndex < commandHistory.length - 1) {
                historyIndex++;
                this.value = commandHistory[commandHistory.length - 1 - historyIndex];
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault(); // Prevent cursor movement
            if (historyIndex > 0) {
                historyIndex--;
                this.value = commandHistory[commandHistory.length - 1 - historyIndex];
            } else if (historyIndex === 0) {
                historyIndex = -1;
                this.value = '';
            }
        }
    });

    // Add event listeners for macro variable inputs (Enter key only, removed blur)
    ['CHIP_X', 'CHIP_Y', 'STAGE_X'].forEach(varName => {
        const input = document.getElementById(varName);
        if (input) {
            input.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    updateMacroVariables();
                }
            });
        }
    });
    
    // Request current macro variables on load
    setTimeout(() => {
        sendWebSocketMessage('get_macro_variables', {});
    }, 500);

});

function updateMacroVariables() {
    const variables = {
        CHIP_X: parseFloat(document.getElementById('CHIP_X').value),
        CHIP_Y: parseFloat(document.getElementById('CHIP_Y').value),
        STAGE_X: parseFloat(document.getElementById('STAGE_X').value)
    };
    
    // Validate the values
    if (isNaN(variables.CHIP_X) || isNaN(variables.CHIP_Y) || isNaN(variables.STAGE_X)) {
        addLog('Invalid macro variable values');
        return;
    }
    
    macroVariables = variables;
    sendWebSocketMessage('update_macro_variables', { variables: variables });
}

function saveVariablesManually() {
    updateMacroVariables();
}

function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = function() {
        updateConnectionStatus(false);
        addLog('Connected to web server');

        sendWebSocketMessage('get_arduino_status', {});
        loadMacroList();
        configureButtons();
    };

    ws.onclose = function() {
        updateConnectionStatus(false);

        configSwitches(false);

        addLog('Disconnected from server');
        // Attempt to reconnect after 3 seconds
        setTimeout(initializeWebSocket, 3000);
    };

    ws.onerror = function(error) {
        addLog('WebSocket error: ' + error);
    };
    
    ws.onmessage = function(event) {
        try {
            const message = JSON.parse(event.data);
            const eventType = message.event;
            const data = message.data;
            
            switch(eventType) {
                case 'arduino_connection_status':
                    updateConnectionStatus(data.connected);
                    addLog(data.connected ? 'Arduino connected' : 'Arduino disconnected');
                    configSwitches(data.connected);
                    break;
                    
                case 'connection_status':
                    updateConnectionStatus(data.connected);
                    break;
                    
                case 'temperature_update':
                    currentTemp = data.temperature || 0;
                    targetTemp = data.set_temperature || 0;
                    updateTemperatureDisplay();
                    updateTempChart();
                    break;
                    
                case 'position_update':
                    position = data;
                    updatePositionDisplay();
                    break;
                    
                case 'motor_states_update':
                    motorStates = data;
                    updateMotorStatesDisplay();
                    break;

                case 'macro_state_update':
                    macroStates = data;
                    console.log(macroStates);
                    updateMacroDisplay(data['macro']);
                    break;
                case 'macro_queue_state_update':
                    macroQueueStates = data;
                    updateSelectorDisplay();
                    break;
                case 'pneumatics_update':
                    pneumatics = data;
                    updatePneumaticsDisplay();
                    break;
                    
                case 'vacuums_update':
                    vacuums = data;
                    updateVacuumsDisplay();
                    break;
                    
                case 'tape_update':
                    tape = data;
                    updateTapeDisplay();
                    break;
                    
                case 'estop_update':
                    eStopTriggered = data.triggered;
                    updateEmergencyStopDisplay();
                    break;
                    
                case 'command_sent':
                    addLog(`Sent: ${data.command}`);
                    break;

                case 'macro_queue_completed':
                    addLog('All macros completed!')
                    removePlayPause()  
                    break;
                    
                case 'macro_queue_stopped':
                    addLog('Macro queue stopped')
                    break;

                case 'macro_queue_paused':
                    addLog('Macro execution paused');
                    break;

                case 'machine_response':
                    addLog(`Response: ${data.response}`);
                    break;

                case 'macro_list':
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
                    break;
                    
                case 'macro_created':
                    addLog(`Macro created: ${data.name}`);
                    loadMacroList();
                    break;
                    
                case 'macro_deleted':
                    addLog(`Macro deleted: ${data.name}`);
                    loadMacroList();
                    break;
                    
                case 'macro_executed':
                    addLog(`Executing macro: ${data.name}`);
                    break;
                    
                case 'macro_error':
                    addLog(`Macro error: ${data.error}`);
                    break;

                case 'macro_content':
                    document.getElementById('macroContent').value = data.content || getMacroTemplate();
                    openMacroEditor();
                    break;

                case 'macro_completed':
                    addLog(`Macro completed: ${data.name}`);
                    break;

                case 'running_chip':
                    addLog(`Running macro: ${data.name}`)
                    break;

                case 'macro_stopped':
                    addLog('Macro execution stopped');
                    break;

                case 'macro_variables_updated':
                    macroVariables = data.variables || data;
                    const changes = data.changes;
                    
                    // Update input fields if they exist and not currently being edited
                    Object.keys(macroVariables).forEach(key => {
                        const input = document.getElementById(key);
                        if (input && document.activeElement !== input) {
                            input.value = macroVariables[key];
                        }
                    });
                    
                    // Log the changes to console
                    if (changes) {
                        addLog(`Variables saved: ${changes}`);
                    } else {
                        addLog('Macro variables updated');
                    }
                    break;
                    
                default:
                    console.log('Unknown event type:', eventType, data);
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    };
}

function sendWebSocketMessage(event, data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ event: event, data: data }));
    } else {
        console.warn('WebSocket not connected, cannot send message:', event);
    }
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

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
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

function updateSelectorDisplay(){
    let running = macroQueueStates['macroQueueRunning'];
    let paused = macroQueueStates['paused']

    if (!running && !paused){
        pauseButton();
        removePlayPause();
    } 
    else if (!running && paused){
        resumeButton();
    }
    else if  (running && !paused){
        pauseButton();
        addPlayPause();
    }
}

function updateMacroDisplay(macro){
    //update macros so they show pause and stop when theyre running


    const macroClass = macro.replace(/ /g, '-');
    const macroActions = document.querySelector(`.${macroClass}.macro-actions`)

    //not paused or running
    if (!macroStates['macroRunning'] && !macroStates['paused']){
        macroActions.innerHTML = `
            <div class="${macroClass} macro-actions">
                <button class="button btn-success" onclick="runMacro('${macro}')">Run</button>
                <button class="button btn-warning" onclick="editMacro('${macro}')">Edit</button>
                <button class="button btn-danger" onclick="deleteMacro('${macro}')">Delete</button>
            </div>
        `;
    }

    //running, we switch the macroactions to stop buttons
    else if (macroStates['macroRunning'] && !macroStates['paused']){
            macroActions.innerHTML = `
            <div class="${macroClass} macro-actions">
                <button class="button btn-danger" onclick="stopMacro()">STOP MACRO</button>
            </div>
        `;
    }

    //paused



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

        const toggle = document.getElementById(`motorToggle${axis.toUpperCase()}`);
        if (toggle) {
            toggle.checked = (motorStates[axis] === "MOTOR_READY" || motorStates[axis] === "MOTOR_MOVING");
        }
    });
}


function updateMotorSliders() {
    const states = {
        X: motorStates.x,
        Y: motorStates.y
    };

    Object.entries(states).forEach(([axis, state]) => {
        const slider = document.getElementById(`togBtn${axis}`);
        if (!slider) return;

        slider.checked = (state === "MOTOR_READY" || state === "MOTOR_MOVING");
    });
}



// Modified updatePneumaticsDisplay to update sliders
function updatePneumaticsDisplay() {
    Object.keys(pneumatics).forEach(component => {
        const toggle = document.getElementById(`toggle${capitalize(component)}`);
        if (toggle) {
            toggle.checked = pneumatics[component];
        }
    });
}

// Modified updateVacuumsDisplay to update sliders
function updateVacuumsDisplay() {
    Object.keys(vacuums).forEach(component => {
        const toggle = document.getElementById(`toggle${capitalize(component)}`);
        if (toggle) {
            toggle.checked = vacuums[component];
        }
    });
}


function updateTapeDisplay() {
    document.getElementById('currentTapeSpeed').textContent = tape.speed || 0;
    document.getElementById('currentTapeTorque').textContent = tape.torque || 0;
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

function loadMacroList() {
    sendWebSocketMessage('get_macros', {});
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
        const macroClass = macro.replace(/ /g, '-');

        macroItem.className = 'macro-item';
        macroItem.innerHTML = `
            <span class="macro-name">${macro}</span>
            <div class="${macroClass} macro-actions">
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
    
    sendWebSocketMessage('save_macro', {
        name: currentEditingMacro,
        content: content,
        variables: macroVariables
    });
    closeMacroEditor();
    document.getElementById('newMacroName').value = '';
}

function editMacro(name) {
    currentEditingMacro = name;
    document.getElementById('editingMacroName').textContent = name;
    sendWebSocketMessage('load_macro', { name: name });
}

function runMacro(name) {
    sendWebSocketMessage('run_macro', {
        name: name,
        variables: macroVariables
    });
}


function runChipMacro(name, x, y, stageX) {
    const variables = {
        CHIP_X: x,
        CHIP_Y: y,
        STAGE_X: stageX  // Use the queued value, not current
    };
    sendWebSocketMessage('run_macro', {
        name: name,
        variables: variables
    });
}

function deleteMacro(name) {
    if (confirm(`Are you sure you want to delete macro "${name}"?`)) {
        sendWebSocketMessage('delete_macro', { name: name });
    }
}

function homeAxis(axis) {
    sendWebSocketMessage('home_axis', { axis: axis });
}

function enableAxis(axis) {
    sendWebSocketMessage('enable_axis', { axis: axis });
}

function disableMotor(axis) {
    sendWebSocketMessage('disable_motor', { axis: axis });
}

function moveToPosition(axis) {
    const inputId = axis.toLowerCase() + 'PositionInput';
    const position = parseFloat(document.getElementById(inputId).value);
    sendWebSocketMessage('move_position', { axis: axis, position: position });
}

function controlPneumatic(component, action) {
    sendWebSocketMessage('pneumatic_control', { component: component, action: action });
}

function controlVacuum(component, action) {
    sendWebSocketMessage('vacuum_control', { component: component, action: action });
}

function setTemperature() {
    const temp = parseInt(document.getElementById('tempInput').value);
    sendWebSocketMessage('set_temperature', { temperature: temp });
}

function emergencyStop() {
    sendWebSocketMessage('emergency_stop', {});
}

function runTapeMotor() {
    const speed = parseInt(document.getElementById('tapeSpeed').value);
    const torque = parseInt(document.getElementById('tapeTorque').value);
    const time = parseInt(document.getElementById('tapeTime').value);
    sendWebSocketMessage('tape_motor', { speed: speed, torque: torque, time: time });
}

function stopTapeMotor() {
    sendWebSocketMessage('send_command', { command: 'StopTape' });
}

function sendCustomCommand() {
    const command = document.getElementById('customCommand').value.trim();
    if (command) {
        // Add to history (avoid duplicates)
        if (commandHistory.length === 0 || commandHistory[commandHistory.length - 1] !== command) {
            commandHistory.push(command);
            // Keep only last 50 commands
            if (commandHistory.length > 50) {
                commandHistory.shift();
            }
        }
        
        sendWebSocketMessage('send_command', { command: command });
        document.getElementById('customCommand').value = '';
        historyIndex = -1; // Reset history navigation
    }
}

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
function checkChips(chips){
    let white = false
    for (chip of chips){
        if (!chip.classList.contains('selected')) white = true
    }
    return white;
}

function selectRow(event) {
    const row = event.target;
    const actionSelect = row.textContent.trim();

    const selectedRow = document.querySelectorAll(`.row:nth-child(${11 - actionSelect}) button`);
    const shouldSelect = checkChips(selectedRow);

    if (shouldSelect) {
        for (const chip of selectedRow) {
            if (!chip.classList.contains('selected')) {
                chip.classList.add('selected');
                selectedChips.push(chip.id);
            }
        }
    } else {
        for (const chip of selectedRow) {
            chip.classList.remove('selected');
            const index = selectedChips.indexOf(chip.id);
            if (index !== -1) {
                selectedChips.splice(index, 1);
            }
        }
    }
}



function selectColumn(event) {
    const col = event.target;
    const actionSelect = col.textContent.trim();

    const selectedCol = document.querySelectorAll(`.col-${actionSelect}`);
    const shouldSelect = checkChips(selectedCol);

    if (shouldSelect) {
        for (const chip of selectedCol) {
            if (!chip.classList.contains('selected')) {
                chip.classList.add('selected');
                selectedChips.push(chip.id);
            }
        }
    } else {
        for (const chip of selectedCol) {
            chip.classList.remove('selected');
            const index = selectedChips.indexOf(chip.id);
            if (index !== -1) {
                selectedChips.splice(index, 1);
            }
        }
    }
}

function selectAllChips(){
    const  chips = document.querySelectorAll('.chip')
    const shouldSelect = checkChips(chips);

    if (shouldSelect) {
        for (const chip of chips) {
            if (!chip.classList.contains('selected')) {
                chip.classList.add('selected');
                selectedChips.push(chip.id);
            }
        }
    } else {
        for (const chip of chips) {
            chip.classList.remove('selected');
            const index = selectedChips.indexOf(chip.id);
            if (index !== -1) {
                selectedChips.splice(index, 1);
            }
        }
    }

}



function addPlayPause(){
    let runningButtons = document.querySelectorAll('.macro-running')

    runningButtons.forEach(button =>{
        button.style.display = 'block';

    })

    let notRunning = document.querySelectorAll('.not-running')

    notRunning.forEach(button =>{
        button.style.display = 'none';
    })


}

function removePlayPause(){
    let runningButtons = document.querySelectorAll('.macro-running')

    runningButtons.forEach(button =>{
        button.style.display = 'none';

    })

    let notRunning = document.querySelectorAll('.not-running')

    notRunning.forEach(button =>{
        button.style.display = '';
    })


}

function submitChips() {
    if (selectedChips.length === 0) {
        addLog('No chips selected');
        return;
    }



    const columns = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5};
    const actionSelect = document.querySelector('#action').value;
    
    if (!actionSelect) {
        addLog('No macro selected');
        return;
    }

    const capturedStageX = macroVariables.STAGE_X;

    macroQueue = [];
    for (let chip of selectedChips) {
        const column = chip[0];
        const row = parseInt(chip.slice(1));
        
        // USE VARIABLES FROM macroVariables (loaded from variables.json)
        let xcor = macroVariables.CHIP_X + (row - 1) * 11.75;
        let ycor = macroVariables.CHIP_Y - (columns[column] * 11.75);

        macroQueue.push({
            name: chip,
            macro: actionSelect,
            variables: {
                CHIP_X: xcor,
                CHIP_Y: ycor,
                STAGE_X: capturedStageX  // Use the passed value, not current
            }
        });
    }


    sendMacroQueue(macroQueue) 


    addLog(`Queued ${macroQueue.length} chips for sequential processing`);
    
}


function sendMacroQueue(queue){
    sendWebSocketMessage('send_macro_queue', {
        queue: queue
    });

}
function stopMacro(){
    sendWebSocketMessage('stop_macro')
}
function stopMacroQueue() {
    sendWebSocketMessage('stop_macro_queue', {});
    
}

function pauseMacroQueue(){
    sendWebSocketMessage('pause_macro_queue', {});
}

function resumeMacroQueue(){
    addLog('Macro queue resumed')
    sendWebSocketMessage('resume_macro_queue', {});
}

function pauseButton(){
    const btn = document.querySelector('#pauseChips');
    btn.innerHTML = 'Pause macro';
    btn.classList.replace('btn-success', 'btn-warning');
    btn.onclick = pauseMacroQueue;
}

function resumeButton(){
    const btn = document.querySelector('#pauseChips');
    btn.innerHTML = 'Resume';
    btn.classList.replace('btn-warning', 'btn-success');
    btn.onclick = resumeMacroQueue;

}


function dropdownClick(event){
    let dropdown = event.target;

    if (dropdown.classList.contains('hide')){
        dropdown.classList.remove('hide')
    }
    else{
        dropdown.classList.add('hide')
    }

    let container = dropdown.closest('.card');

    let next = container.querySelector('h2').nextElementSibling;

    while (next){
        if (next.style.display == 'none'){
            next.style.display = '';
        
        }
        else{
            next.style.display = 'none';

        }
        next =  next.nextElementSibling;
    }


}

function isScrolledToBottom(element, threshold = 50) {
    return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
}

function addLog(message) {
    const console = document.getElementById('console');
    const shouldScroll = isScrolledToBottom(console);
    const timestamp = new Date().toLocaleTimeString();
    const logLine = document.createElement('div');
    logLine.className = 'console-line';
    logLine.textContent = `[${timestamp}] ${message}`;
    console.appendChild(logLine);
    
    if (shouldScroll) {
        console.scrollTop = console.scrollHeight;
    }
    
    while (console.children.length > 200) {
        console.removeChild(console.firstChild);
    }
}

function configSwitches(connected){
    let switches = document.querySelectorAll('.switch');
    let available = document.querySelectorAll('.switchPlaceholder');

    switches.forEach(toggle => {
        if (!connected) toggle.style.display = 'none';
        else toggle.style.display = 'block';
    })

    available.forEach(toggle => {
        if (!connected) toggle.style.display = 'block';
        else toggle.style.display = 'none';
    })
}