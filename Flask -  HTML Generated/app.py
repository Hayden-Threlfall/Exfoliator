from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import socket
import threading
import time
import json
import queue
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'exfoliator-secure-key-2024'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration
MACHINE_HOST = '192.168.3.100'  # Machine IP
MACHINE_PORT = 23               # TCP port for machine
SERVER_HOST = '192.168.3.120'   # Raspberry Pi server IP

class MachineConnection:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.command_queue = queue.Queue()
        self.temperature = 0
        self.set_temperature = 0
        self.position = {'x': 0, 'y': 0}
        self.motor_states = {'x': 'MOTOR_DISABLED', 'y': 'MOTOR_DISABLED'}
        self.tape = {'speed': 0, 'torque': 0}
        self.pneumatics = {
            'nozzle': False,
            'stage': False, 
            'stamp': False
        }
        self.vacuums = {
            'vacnozzle': False,
            'chuck': False
        }
        self.last_ping_time = time.time()
        self.ping_response_received = False
        self.estop_triggered = False
        
    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((MACHINE_HOST, MACHINE_PORT))
            self.connected = True
            logging.info(f"Connected to machine at {MACHINE_HOST}:{MACHINE_PORT}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to machine: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        if self.socket:
            self.socket.close()
        self.connected = False
        
    def send_command(self, command):
        if not self.connected:
            return False
        try:
            self.socket.send(f"{command}\n".encode())
            logging.info(f"Sent command: {command}")
            return True
        except Exception as e:
            logging.error(f"Failed to send command: {e}")
            self.connected = False
            return False
    
    def read_response(self):
        if not self.connected:
            return None
        try:
            self.socket.settimeout(1.0)
            response = self.socket.recv(1024).decode().strip()
            return response
        except socket.timeout:
            return None
        except Exception as e:
            logging.error(f"Failed to read response: {e}")
            return None

machine = MachineConnection()

def machine_communication_thread():
    """Background thread for machine communication"""
    while True:
        try:
            # Process command queue
            if not machine.command_queue.empty():
                command = machine.command_queue.get()
                success = machine.send_command(command)
                
                if success:
                    response = machine.read_response()
                    if response:
                        # Try to parse JSON status updates
                        if response.startswith('{') and response.endswith('}'):
                            parse_json_status(response)
                        elif response == 'pong':
                            machine.ping_response_received = True
                            logging.info("Ping successful")
                        else:
                            socketio.emit('machine_response', {'response': response})
                
            # Handle ping every 30 seconds
            current_time = time.time()
            if current_time - machine.last_ping_time >= 30:
                machine.ping_response_received = False
                machine.send_command("ping")
                machine.last_ping_time = current_time
                
                # Check ping response after 2 seconds
                time.sleep(2)
                if not machine.ping_response_received:
                    machine.connected = False
                    socketio.emit('connection_status', {'connected': False})
                    logging.info("Ping failed - disconnected")
                
            # Read any incoming JSON status updates
            if machine.connected:
                response = machine.read_response()
                if response and response.startswith('{') and response.endswith('}'):
                    parse_json_status(response)
            
            time.sleep(0.1)  # Check more frequently for JSON updates
            
        except Exception as e:
            logging.error(f"Communication thread error: {e}")
            time.sleep(1)

def parse_json_status(json_string):
    """Parse JSON status updates from machine"""
    try:
        data = json.loads(json_string)
        
        # Update position
        if 'x' in data and 'y' in data:
            machine.position['x'] = data['x']
            machine.position['y'] = data['y']
            socketio.emit('position_update', machine.position)
        
        # Update motor states
        motor_states_updated = False
        if 'stateX' in data:
            machine.motor_states['x'] = data['stateX']
            motor_states_updated = True
        if 'stateY' in data:
            machine.motor_states['y'] = data['stateY']
            motor_states_updated = True
        
        if motor_states_updated:
            socketio.emit('motor_states_update', machine.motor_states)
        
        # Update tape motor status
        if 'tape' in data:
            tape_data = data['tape']
            if isinstance(tape_data, list) and len(tape_data) >= 2:
                machine.tape['speed'] = tape_data[0]
                machine.tape['torque'] = tape_data[1]
                socketio.emit('tape_update', machine.tape)
        
        # Update pneumatics
        pneumatics_updated = False
        if 'nozzle' in data:
            machine.pneumatics['nozzle'] = data['nozzle']
            pneumatics_updated = True
        if 'stage' in data:
            machine.pneumatics['stage'] = data['stage']
            pneumatics_updated = True
        if 'stamp' in data:
            machine.pneumatics['stamp'] = data['stamp']
            pneumatics_updated = True
        
        if pneumatics_updated:
            socketio.emit('pneumatics_update', machine.pneumatics)
        
        # Update vacuums
        vacuums_updated = False
        if 'vacnozzle' in data:
            machine.vacuums['vacnozzle'] = data['vacnozzle']
            vacuums_updated = True
        if 'chuck' in data:
            machine.vacuums['chuck'] = data['chuck']
            vacuums_updated = True
        
        if vacuums_updated:
            socketio.emit('vacuums_update', machine.vacuums)
        
        # Update temperatures
        temp_updated = False
        if 'temp' in data:
            machine.temperature = data['temp']
            temp_updated = True
        if 'settemp' in data:
            machine.set_temperature = data['settemp']
            temp_updated = True
        
        if temp_updated:
            socketio.emit('temperature_update', {
                'temperature': machine.temperature,
                'set_temperature': machine.set_temperature
            })
        # Update emergency stop status
        if 'eStopTriggered' in data:
            machine.estop_triggered = data['eStopTriggered']
            socketio.emit('estop_update', {'triggered': machine.estop_triggered})
            
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON status: {e}")
    except Exception as e:
        logging.error(f"Error processing JSON status: {e}")

def parse_machine_response(response):
    """Parse machine responses to update status (legacy)"""
    # This function is now mostly handled by JSON parsing
    pass

@app.route('/')
def index():
    return send_file('control.html')

@app.route('/connect', methods=['POST'])
def connect_machine():
    success = machine.connect()
    return jsonify({'success': success, 'connected': machine.connected})

@app.route('/disconnect', methods=['POST'])
def disconnect_machine():
    machine.disconnect()
    return jsonify({'success': True, 'connected': machine.connected})

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        'connected': machine.connected,
        'temperature': machine.temperature,
        'set_temperature': machine.set_temperature,
        'position': machine.position,
        'motor_states': machine.motor_states,
        'pneumatics': machine.pneumatics,
        'vacuums': machine.vacuums,
        'tape': machine.tape
    })

@socketio.on('connect')
def handle_connect():
    emit('connection_status', {'connected': machine.connected})
    emit('temperature_update', {
        'temperature': machine.temperature,
        'set_temperature': machine.set_temperature
    })
    emit('position_update', machine.position)
    emit('motor_states_update', machine.motor_states)
    emit('pneumatics_update', machine.pneumatics)
    emit('vacuums_update', machine.vacuums)
    emit('tape_update', machine.tape)

@socketio.on('send_command')
def handle_command(data):
    command = data.get('command', '')
    if command:
        machine.command_queue.put(command)
        emit('command_sent', {'command': command})

@socketio.on('move_position')
def handle_move_position(data):
    axis = data.get('axis')
    position = data.get('position', 0)
    
    if axis == 'X':
        command = f"MoveX {position}"
    elif axis == 'Y':
        command = f"MoveY {position}"
    else:
        return
    
    machine.command_queue.put(command)
    emit('command_sent', {'command': command})

@socketio.on('home_axis')
def handle_home(data):
    axis = data.get('axis', '')
    
    if axis == 'X':
        command = "HomeX"
    elif axis == 'Y':
        command = "HomeY"
    else:
        command = "Home"  # Home all axes
    
    machine.command_queue.put(command)
    emit('command_sent', {'command': command})

@socketio.on('set_temperature')
def handle_temperature(data):
    temperature = data.get('temperature', 0)
    command = f"SetTemperature {temperature}"
    machine.command_queue.put(command)
    emit('command_sent', {'command': command})

@socketio.on('get_temperature')
def handle_get_temperature():
    machine.command_queue.put("GetTemperature")
    emit('command_sent', {'command': 'GetTemperature'})

@socketio.on('pneumatic_control')
def handle_pneumatic(data):
    component = data.get('component')  # 'nozzle', 'stage', 'stamp'
    action = data.get('action')        # 'extend', 'retract'
    
    command_map = {
        'nozzle': {'extend': 'ExtendNozzle', 'retract': 'RetractNozzle'},
        'stage': {'extend': 'ExtendChipStage', 'retract': 'RetractChipStage'},
        'stamp': {'extend': 'ExtendStamp', 'retract': 'RetractStamp'}
    }
    
    if component in command_map and action in command_map[component]:
        command = command_map[component][action]
        machine.command_queue.put(command)
        emit('command_sent', {'command': command})

@socketio.on('vacuum_control')
def handle_vacuum(data):
    component = data.get('component')  # 'vacnozzle', 'chuck'
    action = data.get('action')        # 'on', 'off'
    
    command_map = {
        'vacnozzle': {'on': 'VacNozzleOn', 'off': 'VacNozzleOff'},
        'chuck': {'on': 'ChuckOn', 'off': 'ChuckOff'}
    }
    
    if component in command_map and action in command_map[component]:
        command = command_map[component][action]
        machine.command_queue.put(command)
        emit('command_sent', {'command': command})

@socketio.on('disable_motor')
def handle_disable_motor(data):
    axis = data.get('axis')  # 'X' or 'Y'
    
    if axis == 'X':
        command = "DisableX"
    elif axis == 'Y':
        command = "DisableY"
    else:
        return
    
    machine.command_queue.put(command)
    emit('command_sent', {'command': command})

@socketio.on('emergency_stop')
def handle_emergency_stop():
    machine.command_queue.put("STOP")
    emit('command_sent', {'command': 'STOP - EMERGENCY STOP'})

@socketio.on('tape_motor')
def handle_tape_motor(data):
    speed = data.get('speed', 100)
    torque = data.get('torque', 50)
    time_ms = data.get('time', 1000)
    
    command = f"Tape {speed} {torque} {time_ms}"
    machine.command_queue.put(command)
    emit('command_sent', {'command': command})

# Start the communication thread
communication_thread = threading.Thread(target=machine_communication_thread, daemon=True)
communication_thread.start()

if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Try to connect to machine on startup
    machine.connect()
    
    # Run the Flask app with SocketIO
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)