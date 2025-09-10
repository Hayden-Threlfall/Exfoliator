// Global variables
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

    // Initialize when page loads
    document.addEventListener('DOMContentLoaded', function() {
        initializeSocket();
        initializeChart();
        const chipsContainer = document.querySelector('.chips');
        if (chipsContainer) {
            chipsContainer.addEventListener('click', handleChipSelection);
        }
        // Initialize all status indicators as red (inactive)
        updatePneumaticsDisplay();
        updateVacuumsDisplay();
    });

    function initializeSocket() {
        socket = io();
        
        socket.on('connect', function() {
            updateConnectionStatus(true);
            addLog('Connected to server');
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
        
        // Don't overwrite user inputs while they're typing
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
        
        // Keep only last 10 lines
        while (console.children.length > 10) {
            console.removeChild(console.firstChild);
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
        socket.emit('stop_tape');
    }

    function sendCustomCommand() {
        const command = document.getElementById('customCommand').value;
        if (command.trim()) {
            socket.emit('send_command', { command: command });
            document.getElementById('customCommand').value = '';
        }
    }

    // Allow Enter key to send custom commands
    document.getElementById('customCommand').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendCustomCommand();
        }
    });

    // Chip selection functions
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


    function submitChips(action) {
        const actionSelect = document.getElementById('action').value;

        selectedChips.sort();
        console.log(selectedChips)
        console.log(action)
        socket.emit('move_to_chip', { chips: selectedChips, action: actionSelect });
    }