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
ARDUINO_HOST = '192.168.3.100'  # Arduino IP
TCP_SERVER_PORT = 1053          # TCP port to listen on (matches your requirement)
HTTP_PORT = 5000               # HTTP port for Flask (matches your requirement)
SERVER_HOST = '192.168.3.120'   # Raspberry Pi server IP

class ArduinoTCPServer:
    def __init__(self):
        self.server_socket = None
        self.client_socket = None
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
        # PING/PONG heartbeat tracking
        self.last_ping_sent = time.time()
        self.ping_interval = 2.0  # Send PING every 2 seconds
        self.last_response_received = time.time()  # Any response (JSON, PONG, etc.)
        self.response_timeout = 7.0  # Consider disconnected if no response for 7 seconds
        self.estop_triggered = False
        
    def start_server(self):
        try:
            if self.server_socket:
                self.server_socket.close()
            
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', TCP_SERVER_PORT))
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)  # Non-blocking accept
            logging.info(f"TCP Server listening on port {TCP_SERVER_PORT}")
            return True
        except Exception as e:
            logging.error(f"Failed to start TCP server: {e}")
            return False
    
    def wait_for_connection(self):
        try:
            if not self.server_socket:
                return False
                
            self.client_socket, addr = self.server_socket.accept()
            self.client_socket.settimeout(1.0)  # Non-blocking recv
            self.connected = True
            self.last_ping_sent = time.time()
            self.last_response_received = time.time()  # Reset heartbeat timer
            logging.info(f"Arduino connected from {addr}")
            socketio.emit('connection_status', {'connected': True})
            return True
        except socket.timeout:
            return False
        except Exception as e:
            logging.error(f"Failed to accept connection: {e}")
            return False
    
    def disconnect(self):
        self.connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        socketio.emit('connection_status', {'connected': False})
        
    def send_command(self, command):
        if not self.connected or not self.client_socket:
            logging.warning(f"Cannot send command '{command}' - Arduino not connected")
            return False
        try:
            message = f"{command}\n"
            self.client_socket.send(message.encode())
            logging.info(f"Sent command: {command}")
            return True
        except Exception as e:
            logging.error(f"Failed to send command '{command}': {e}")
            self.connected = False
            socketio.emit('connection_status', {'connected': False})
            return False
    
    def read_response(self):
        if not self.connected or not self.client_socket:
            return None
        try:
            response = self.client_socket.recv(1024).decode().strip()
            if response:
                logging.debug(f"Received response: {response}")
                # Update heartbeat for ANY response received
                self.last_response_received = time.time()
            return response
        except socket.timeout:
            return None
        except Exception as e:
            if e.errno != 11:  # Ignore "Resource temporarily unavailable" 
                logging.error(f"Failed to read response: {e}")
                self.connected = False
                socketio.emit('connection_status', {'connected': False})
            return None
    
    def should_send_ping(self):
        """Check if it's time to send a PING"""
        return (time.time() - self.last_ping_sent) >= self.ping_interval
    
    def send_ping(self):
        """Send PING command and update timestamp"""
        if self.send_command("PING"):
            self.last_ping_sent = time.time()
            logging.debug("PING sent")
            return True
        return False
    
    def check_connection_health(self):
        """Check if we've received any response recently enough to consider connection alive"""
        if not self.connected:
            return False
            
        time_since_last_response = time.time() - self.last_response_received
        if time_since_last_response > self.response_timeout:
            logging.warning(f"Connection timeout - {time_since_last_response:.2f}s since last response")
            self.disconnect()
            return False
        return True

arduino_server = ArduinoTCPServer()

def arduino_communication_thread():
    """Background thread for Arduino communication"""
    while True:
        try:
            # Try to start server if not connected
            if not arduino_server.connected:
                if not arduino_server.start_server():
                    time.sleep(5)
                    continue
                    
                # Try to accept connection (non-blocking)
                if not arduino_server.wait_for_connection():
                    time.sleep(0.1)
                    continue
            
            # Send PING if it's time
            if arduino_server.connected and arduino_server.should_send_ping():
                arduino_server.send_ping()
            
            # Process command queue
            while not arduino_server.command_queue.empty():
                command = arduino_server.command_queue.get()
                success = arduino_server.send_command(command)
                
                if success:
                    # Wait a bit for response
                    time.sleep(0.1)
                    response = arduino_server.read_response()
                    if response:
                        # Try to parse JSON status updates
                        if response.startswith('{') and response.endswith('}'):
                            parse_json_status(response)
                        elif response == "PONG":
                            logging.debug("PONG received")
                            # PONG response already updated last_response_received in read_response()
                        else:
                            socketio.emit('machine_response', {'response': response})
                            logging.info(f"Arduino response: {response}")
                
            # Check connection health
            if arduino_server.connected:
                if not arduino_server.check_connection_health():
                    logging.warning("Connection health check failed - Arduino disconnected")
                    continue
                
                # Read any incoming responses (JSON, PONG, etc.)
                response = arduino_server.read_response()
                if response:
                    if response.startswith('{') and response.endswith('}'):
                        parse_json_status(response)
                    elif response == "PONG":
                        logging.debug("PONG received")
                        # Response timestamp already updated in read_response()
                    else:
                        socketio.emit('machine_response', {'response': response})
                        logging.info(f"Arduino response: {response}")
            
            time.sleep(0.1)  # Check frequently for responses
            
        except Exception as e:
            logging.error(f"Communication thread error: {e}")
            arduino_server.connected = False
            socketio.emit('connection_status', {'connected': False})
            time.sleep(1)

def parse_json_status(json_string):
    """Parse JSON status updates from Arduino"""
    try:
        logging.debug(f"Parsing JSON: {json_string}")
        data = json.loads(json_string)
        
        # Note: last_response_received is already updated in read_response() 
        # when we receive ANY response, including JSON
        
        # Update position
        if 'x' in data and 'y' in data:
            arduino_server.position['x'] = float(data['x'])
            arduino_server.position['y'] = float(data['y'])
            socketio.emit('position_update', arduino_server.position)
            logging.debug(f"Position update: {arduino_server.position}")
        
        # Update motor states
        motor_states_updated = False
        if 'stateX' in data:
            arduino_server.motor_states['x'] = str(data['stateX'])
            motor_states_updated = True
        if 'stateY' in data:
            arduino_server.motor_states['y'] = str(data['stateY'])
            motor_states_updated = True
        
        if motor_states_updated:
            socketio.emit('motor_states_update', arduino_server.motor_states)
            logging.debug(f"Motor states update: {arduino_server.motor_states}")
        
        # Update tape motor status
        if 'tape' in data:
            tape_data = data['tape']
            if isinstance(tape_data, list) and len(tape_data) >= 2:
                arduino_server.tape['speed'] = int(tape_data[0])
                arduino_server.tape['torque'] = int(tape_data[1])
                socketio.emit('tape_update', arduino_server.tape)
                logging.debug(f"Tape update: {arduino_server.tape}")
        
        # Update pneumatics
        pneumatics_updated = False
        if 'nozzle' in data:
            arduino_server.pneumatics['nozzle'] = bool(data['nozzle'])
            pneumatics_updated = True
        if 'stage' in data:
            arduino_server.pneumatics['stage'] = bool(data['stage'])
            pneumatics_updated = True
        if 'stamp' in data:
            arduino_server.pneumatics['stamp'] = bool(data['stamp'])
            pneumatics_updated = True
        
        if pneumatics_updated:
            socketio.emit('pneumatics_update', arduino_server.pneumatics)
            logging.debug(f"Pneumatics update: {arduino_server.pneumatics}")
        
        # Update vacuums
        vacuums_updated = False
        if 'vacnozzle' in data:
            arduino_server.vacuums['vacnozzle'] = bool(data['vacnozzle'])
            vacuums_updated = True
        if 'chuck' in data:
            arduino_server.vacuums['chuck'] = bool(data['chuck'])
            vacuums_updated = True
        
        if vacuums_updated:
            socketio.emit('vacuums_update', arduino_server.vacuums)
            logging.debug(f"Vacuums update: {arduino_server.vacuums}")
        
        # Update temperatures
        temp_updated = False
        if 'temp' in data:
            arduino_server.temperature = float(data['temp'])
            temp_updated = True
        if 'settemp' in data:
            arduino_server.set_temperature = float(data['settemp'])
            temp_updated = True
        
        if temp_updated:
            socketio.emit('temperature_update', {
                'temperature': arduino_server.temperature,
                'set_temperature': arduino_server.set_temperature
            })
            logging.debug(f"Temperature update: {arduino_server.temperature}°C (target: {arduino_server.set_temperature}°C)")
        
        # Update emergency stop status
        if 'eStopTriggered' in data:
            arduino_server.estop_triggered = bool(data['eStopTriggered'])
            socketio.emit('estop_update', {'triggered': arduino_server.estop_triggered})
            if arduino_server.estop_triggered:
                logging.warning("Emergency stop triggered!")
            
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON status: {json_string} - Error: {e}")
    except Exception as e:
        logging.error(f"Error processing JSON status: {e}")

# Web Routes
@app.route('/')
def index():
    return send_file('control.html')

@app.route('/connect', methods=['POST'])
def connect_machine():
    # Connection is handled automatically by the TCP server
    status = {'success': True, 'connected': arduino_server.connected}
    logging.info(f"Connect request - Status: {status}")
    return jsonify(status)

@app.route('/disconnect', methods=['POST'])
def disconnect_machine():
    arduino_server.disconnect()
    status = {'success': True, 'connected': arduino_server.connected}
    logging.info(f"Disconnect request - Status: {status}")
    return jsonify(status)

@app.route('/status', methods=['GET'])
def get_status():
    status = {
        'connected': arduino_server.connected,
        'temperature': arduino_server.temperature,
        'set_temperature': arduino_server.set_temperature,
        'position': arduino_server.position,
        'motor_states': arduino_server.motor_states,
        'pneumatics': arduino_server.pneumatics,
        'vacuums': arduino_server.vacuums,
        'tape': arduino_server.tape
    }
    logging.debug(f"Status request: {status}")
    return jsonify(status)

# SocketIO Event Handlers with Button Press Logging
@socketio.on('connect')
def handle_connect():
    logging.info("Client connected to SocketIO")
    emit('connection_status', {'connected': arduino_server.connected})
    emit('temperature_update', {
        'temperature': arduino_server.temperature,
        'set_temperature': arduino_server.set_temperature
    })
    emit('position_update', arduino_server.position)
    emit('motor_states_update', arduino_server.motor_states)
    emit('pneumatics_update', arduino_server.pneumatics)
    emit('vacuums_update', arduino_server.vacuums)
    emit('tape_update', arduino_server.tape)

@socketio.on('disconnect')
def handle_disconnect():
    logging.info("Client disconnected from SocketIO")

@socketio.on('send_command')
def handle_command(data):
    command = data.get('command', '')
    logging.info(f"Button Press: Raw command '{command}' received from web interface")
    
    if command:
        if arduino_server.connected:
            arduino_server.command_queue.put(command)
            logging.info(f"Button Press: Command '{command}' queued for Arduino")
            emit('command_sent', {'command': command, 'status': 'queued'})
        else:
            logging.warning(f"Button Press: Command '{command}' received but Arduino not connected")
            emit('command_sent', {'command': command, 'status': 'not_connected'})
    else:
        logging.warning("Button Press: Empty command received")

@socketio.on('stop_command')
def handle_stop_command():
    logging.warning("Button Press: STOP command activated!")
    
    if arduino_server.connected:
        arduino_server.command_queue.put("STOP")
        logging.warning("Button Press: STOP command queued for Arduino")
        emit('command_sent', {'command': 'STOP', 'status': 'queued'})
    else:
        logging.warning("Button Press: STOP command requested but Arduino not connected")
        emit('command_sent', {'command': 'STOP', 'status': 'not_connected'})

@socketio.on('move_position')
def handle_move_position(data):
    axis = data.get('axis')
    position = data.get('position', 0)
    
    logging.info(f"Button Press: Move {axis} axis to position {position}")
    
    if axis == 'X':
        command = f"MoveX {position}"
    elif axis == 'Y':
        command = f"MoveY {position}"
    else:
        logging.warning(f"Button Press: Invalid axis '{axis}' for move command")
        return
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Move command '{command}' queued for Arduino")
        emit('command_sent', {'command': command, 'status': 'queued'})
    else:
        logging.warning(f"Button Press: Move command '{command}' received but Arduino not connected")
        emit('command_sent', {'command': command, 'status': 'not_connected'})

@socketio.on('enable_axis')
def handle_enable_axis(data):
    axis = data.get('axis')  # 'X' or 'Y'
    
    logging.info(f"Button Press: Enable {axis} axis")
    
    if axis == 'X':
        command = "EnableX"
    elif axis == 'Y':
        command = "EnableY"
    else:
        logging.warning(f"Button Press: Invalid axis '{axis}' for enable axis")
        return
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Enable axis command '{command}' queued for Arduino")
        emit('command_sent', {'command': command, 'status': 'queued'})
    else:
        logging.warning(f"Button Press: Enable axis command '{command}' received but Arduino not connected")
        emit('command_sent', {'command': command, 'status': 'not_connected'})

@socketio.on('set_temperature')
def handle_temperature(data):
    temperature = data.get('temperature', 0)
    
    logging.info(f"Button Press: Set temperature to {temperature}°C")
    
    command = f"SetTemperature {temperature}"
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Temperature command '{command}' queued for Arduino")
        emit('command_sent', {'command': command, 'status': 'queued'})
    else:
        logging.warning(f"Button Press: Temperature command '{command}' received but Arduino not connected")
        emit('command_sent', {'command': command, 'status': 'not_connected'})

@socketio.on('get_temperature')
def handle_get_temperature():
    logging.info("Button Press: Get temperature requested")
    
    if arduino_server.connected:
        arduino_server.command_queue.put("GetTemperature")
        logging.info("Button Press: GetTemperature command queued for Arduino")
        emit('command_sent', {'command': 'GetTemperature', 'status': 'queued'})
    else:
        logging.warning("Button Press: GetTemperature requested but Arduino not connected")
        emit('command_sent', {'command': 'GetTemperature', 'status': 'not_connected'})

@socketio.on('pneumatic_control')
def handle_pneumatic(data):
    component = data.get('component')  # 'nozzle', 'stage', 'stamp'
    action = data.get('action')        # 'extend', 'retract'
    
    logging.info(f"Button Press: Pneumatic control - {component} {action}")
    
    command_map = {
        'nozzle': {'extend': 'ExtendNozzle', 'retract': 'RetractNozzle'},
        'stage': {'extend': 'ExtendChipStage', 'retract': 'RetractChipStage'},
        'stamp': {'extend': 'ExtendStamp', 'retract': 'RetractStamp'}
    }
    
    if component in command_map and action in command_map[component]:
        command = command_map[component][action]
        if arduino_server.connected:
            arduino_server.command_queue.put(command)
            logging.info(f"Button Press: Pneumatic command '{command}' queued for Arduino")
            emit('command_sent', {'command': command, 'status': 'queued'})
        else:
            logging.warning(f"Button Press: Pneumatic command '{command}' received but Arduino not connected")
            emit('command_sent', {'command': command, 'status': 'not_connected'})
    else:
        logging.warning(f"Button Press: Invalid pneumatic command - component: {component}, action: {action}")

@socketio.on('vacuum_control')
def handle_vacuum(data):
    component = data.get('component')  # 'vacnozzle', 'chuck'
    action = data.get('action')        # 'on', 'off'
    
    logging.info(f"Button Press: Vacuum control - {component} {action}")
    
    command_map = {
        'vacnozzle': {'on': 'VacNozzleOn', 'off': 'VacNozzleOff'},
        'chuck': {'on': 'ChuckOn', 'off': 'ChuckOff'}
    }
    
    if component in command_map and action in command_map[component]:
        command = command_map[component][action]
        if arduino_server.connected:
            arduino_server.command_queue.put(command)
            logging.info(f"Button Press: Vacuum command '{command}' queued for Arduino")
            emit('command_sent', {'command': command, 'status': 'queued'})
        else:
            logging.warning(f"Button Press: Vacuum command '{command}' received but Arduino not connected")
            emit('command_sent', {'command': command, 'status': 'not_connected'})
    else:
        logging.warning(f"Button Press: Invalid vacuum command - component: {component}, action: {action}")

@socketio.on('disable_motor')
def handle_disable_motor(data):
    axis = data.get('axis')  # 'X' or 'Y'
    
    logging.info(f"Button Press: Disable {axis} motor")
    
    if axis == 'X':
        command = "DisableX"
    elif axis == 'Y':
        command = "DisableY"
    else:
        logging.warning(f"Button Press: Invalid axis '{axis}' for disable motor")
        return
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Disable motor command '{command}' queued for Arduino")
        emit('command_sent', {'command': command, 'status': 'queued'})
    else:
        logging.warning(f"Button Press: Disable motor command '{command}' received but Arduino not connected")
        emit('command_sent', {'command': command, 'status': 'not_connected'})

@socketio.on('emergency_stop')
def handle_emergency_stop():
    logging.warning("Button Press: EMERGENCY STOP activated!")
    
    if arduino_server.connected:
        arduino_server.command_queue.put("STOP")
        logging.warning("Button Press: EMERGENCY STOP command queued for Arduino")
        emit('command_sent', {'command': 'STOP - EMERGENCY STOP', 'status': 'queued'})
    else:
        logging.warning("Button Press: EMERGENCY STOP requested but Arduino not connected")
        emit('command_sent', {'command': 'STOP - EMERGENCY STOP', 'status': 'not_connected'})

@socketio.on('tape_motor')
def handle_tape_motor(data):
    speed = data.get('speed', 100)
    torque = data.get('torque', 50)
    time_ms = data.get('time', 1000)
    
    logging.info(f"Button Press: Tape motor - Speed: {speed}, Torque: {torque}, Time: {time_ms}ms")
    
    command = f"Tape {speed} {torque} {time_ms}"
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Tape motor command '{command}' queued for Arduino")
        emit('command_sent', {'command': command, 'status': 'queued'})
    else:
        logging.warning(f"Button Press: Tape motor command '{command}' received but Arduino not connected")
        emit('command_sent', {'command': command, 'status': 'not_connected'})

# Start the communication thread
communication_thread = threading.Thread(target=arduino_communication_thread, daemon=True)
communication_thread.start()

if __name__ == '__main__':
    # Setup logging with different levels for testing
    logging.basicConfig(
        level=logging.INFO,  # Change to DEBUG for more verbose output
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('flask_app.log')
        ]
    )
    
    logging.info("Starting Flask application...")
    logging.info(f"HTTP Server will run on port {HTTP_PORT}")
    logging.info(f"TCP Server will listen on port {TCP_SERVER_PORT}")
    logging.info("PING/PONG heartbeat system enabled - sending PING every 2 seconds")
    
    # Run the Flask app with SocketIO
    socketio.run(app, host='0.0.0.0', port=HTTP_PORT, debug=False)