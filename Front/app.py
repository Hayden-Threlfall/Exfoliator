from flask import Flask, request, jsonify, send_file, render_template
from flask_sock import Sock
from flask_cors import CORS
import socket
import threading
import time
import json
import queue
import logging
import os
import re
import asyncio

app = Flask(__name__)
app.config['SECRET_KEY'] = 'exfoliator-secure-key-2024'
CORS(app)
sock = Sock(app)

# Configuration
ARDUINO_HOST = '192.168.4.100'  # Arduino IP
TCP_SERVER_PORT = 1053          # TCP port to listen for Arduino
HTTP_PORT = 80               # HTTP port for Flask
HTTP_HOST = '192.168.3.80'     # Flask server IP
SERVER_HOST = '192.168.4.120'   # Raspberry Pi server IP for TCP
MACROS_DIR = 'macros'          # Directory to store macro files

# Create macros directory if it doesn't exist
if not os.path.exists(MACROS_DIR):
    os.makedirs(MACROS_DIR)

# Global variable to store WebSocket connections
websocket_clients = set()

class MacroVariables:
    """Class to hold and manage macro position variables"""
    def __init__(self):
        # Default values
        self.X_AXIS_INITIAL_CHIPWELL = 105.5 
        self.Y_AXIS_INITIAL_CHIPWELL = 4.5
        self.X_AXIS_VACUUM_CHUCK_POSITION = 8
        
        # User-definable values
        self.CHIP_X = self.X_AXIS_INITIAL_CHIPWELL
        self.CHIP_Y = self.Y_AXIS_INITIAL_CHIPWELL
        self.STAGE_X = self.X_AXIS_VACUUM_CHUCK_POSITION
    
    def update(self, chip_x=None, chip_y=None, stage_x=None):
        """Update variables with provided values"""
        if chip_x is not None:
            self.CHIP_X = float(chip_x)
        if chip_y is not None:
            self.CHIP_Y = float(chip_y)
        if stage_x is not None:
            self.STAGE_X = float(stage_x)
    
    def get_variables(self):
        """Get current variable values as dictionary"""
        return {
            'CHIP_X': self.CHIP_X,
            'CHIP_Y': self.CHIP_Y,
            'STAGE_X': self.STAGE_X
        }
    
    def substitute_variables(self, command):
        """Replace variables in command with their values"""
        command = command.replace('CHIP_X', str(self.CHIP_X))
        command = command.replace('CHIP_Y', str(self.CHIP_Y))
        command = command.replace('STAGE_X', str(self.STAGE_X))
        return command

def broadcast_message(event, data):
    """Broadcast message to all connected WebSocket clients"""
    message = json.dumps({'event': event, 'data': data})
    dead_clients = set()
    
    for ws in websocket_clients.copy():
        try:
            ws.send(message)
        except Exception as e:
            logging.error(f"Error sending message to client: {e}")
            dead_clients.add(ws)
    
    # Remove dead connections
    websocket_clients -= dead_clients

class MacroExecutor:
    """Class to handle macro execution"""
    def __init__(self, arduino_server):
        self.arduino_server = arduino_server
        self.variables = MacroVariables()
        self.is_running = False
        self.current_macro = None
        self.stop_requested = False
    
    def save_macro(self, name, content):
        """Save macro to file"""
        try:
            filename = os.path.join(MACROS_DIR, f"{name}.macro")
            with open(filename, 'w') as f:
                f.write(content)
            logging.info(f"Macro saved: {name}")
            return True
        except Exception as e:
            logging.error(f"Failed to save macro {name}: {e}")
            return False
    
    def load_macro(self, name):
        """Load macro from file"""
        try:
            filename = os.path.join(MACROS_DIR, f"{name}.macro")
            with open(filename, 'r') as f:
                content = f.read()
            return content
        except Exception as e:
            logging.error(f"Failed to load macro {name}: {e}")
            return None
    
    def delete_macro(self, name):
        """Delete macro file"""
        try:
            filename = os.path.join(MACROS_DIR, f"{name}.macro")
            if os.path.exists(filename):
                os.remove(filename)
                logging.info(f"Macro deleted: {name}")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to delete macro {name}: {e}")
            return False
    
    def list_macros(self):
        """List all saved macros"""
        try:
            macros = []
            for filename in os.listdir(MACROS_DIR):
                if filename.endswith('.macro'):
                    macros.append(filename[:-6])  # Remove .macro extension
            return sorted(macros)
        except Exception as e:
            logging.error(f"Failed to list macros: {e}")
            return []
    
    def parse_command(self, line):
        """Parse a single macro command line"""
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            return None, None
        
        # Check for delay command
        if line.lower().startswith('delay'):
            match = re.match(r'delay\s+(\d+)', line, re.IGNORECASE)
            if match:
                return 'delay', int(match.group(1))
            return None, None
        
        # Substitute variables in the command
        command = self.variables.substitute_variables(line)
        return 'command', command
    
    async def execute_macro_async(self, name, variables=None):
        """Execute macro asynchronously to avoid blocking"""
        if self.is_running:
            broadcast_message('macro_error', {'error': 'Another macro is already running'})
            return
        
        self.is_running = True
        self.current_macro = name
        self.stop_requested = False
        
        try:
            # Update variables if provided
            if variables:
                self.variables.update(
                    variables.get('CHIP_X'),
                    variables.get('CHIP_Y'),
                    variables.get('STAGE_X')
                )
            
            # Load macro content
            content = self.load_macro(name)
            if not content:
                broadcast_message('macro_error', {'error': f'Macro {name} not found'})
                return
            
            # Parse and execute commands
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if self.stop_requested:
                    logging.info(f"Macro {name} stopped by user")
                    broadcast_message('macro_error', {'error': f'Macro {name} stopped'})
                    break
                
                cmd_type, cmd_data = self.parse_command(line)
                
                if cmd_type == 'delay':
                    logging.info(f"Macro {name}: Delaying {cmd_data}ms")
                    await asyncio.sleep(cmd_data / 1000.0)
                    
                elif cmd_type == 'command':
                    logging.info(f"Macro {name}: Executing {cmd_data}")
                    self.arduino_server.command_queue.put(cmd_data)
                    # Small delay between commands to avoid overwhelming Arduino
                    await asyncio.sleep(0.1)
            
            if not self.stop_requested:
                logging.info(f"Macro {name} completed successfully")
                broadcast_message('macro_completed', {'name': name})
                
        except Exception as e:
            logging.error(f"Error executing macro {name}: {e}")
            broadcast_message('macro_error', {'error': str(e)})
        finally:
            self.is_running = False
            self.current_macro = None
    
    def execute_macro(self, name, variables=None):
        """Execute macro in a separate thread"""
        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.execute_macro_async(name, variables))
            loop.close()
        
        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
    
    def stop_macro(self):
        """Stop currently running macro"""
        if self.is_running:
            self.stop_requested = True
            return True
        return False


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
            self.server_socket.bind((SERVER_HOST, TCP_SERVER_PORT))
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
            self.last_response_received = time.time()
            broadcast_message('arduino_connection_status', {'connected': True})
            logging.info(f"Device connected from {addr}")
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
        broadcast_message('arduino_connection_status', {'connected': False})
        
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
            broadcast_message('arduino_connection_status', {'connected': False})
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
                broadcast_message('arduino_connection_status', {'connected': False})
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
macro_executor = MacroExecutor(arduino_server)

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
                            broadcast_message('machine_response', {'response': response})
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
                        broadcast_message('machine_response', {'response': response})
                        logging.info(f"Arduino response: {response}")
            
            time.sleep(0.1)  # Check frequently for responses
            
        except Exception as e:
            logging.error(f"Communication thread error: {e}")
            arduino_server.connected = False
            broadcast_message('arduino_connection_status', {'connected': False})
            time.sleep(1)

def parse_json_status(json_string):
    """Parse JSON status updates from Arduino"""
    try:
        logging.debug(f"Parsing JSON: {json_string}")
        data = json.loads(json_string)
        
        # Update position
        if 'x' in data and 'y' in data:
            arduino_server.position['x'] = float(data['x'])
            arduino_server.position['y'] = float(data['y'])
            broadcast_message('position_update', arduino_server.position)
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
            broadcast_message('motor_states_update', arduino_server.motor_states)
            logging.debug(f"Motor states update: {arduino_server.motor_states}")
        
        # Update tape motor status
        if 'tape' in data:
            tape_data = data['tape']
            if isinstance(tape_data, list) and len(tape_data) >= 2:
                arduino_server.tape['speed'] = int(tape_data[0])
                arduino_server.tape['torque'] = int(tape_data[1])
                broadcast_message('tape_update', arduino_server.tape)
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
            broadcast_message('pneumatics_update', arduino_server.pneumatics)
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
            broadcast_message('vacuums_update', arduino_server.vacuums)
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
            broadcast_message('temperature_update', {
                'temperature': arduino_server.temperature,
                'set_temperature': arduino_server.set_temperature
            })
            logging.debug(f"Temperature update: {arduino_server.temperature}°C (target: {arduino_server.set_temperature}°C)")
        
        # Update emergency stop status
        if 'eStopTriggered' in data:
            arduino_server.estop_triggered = bool(data['eStopTriggered'])
            broadcast_message('estop_update', {'triggered': arduino_server.estop_triggered})
            if arduino_server.estop_triggered:
                logging.warning("Emergency stop triggered!")
            
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON status: {json_string} - Error: {e}")
    except Exception as e:
        logging.error(f"Error processing JSON status: {e}")

# WebSocket route
@sock.route('/ws')
def websocket_handler(ws):
    """Handle WebSocket connections"""
    websocket_clients.add(ws)
    logging.info("Client connected to WebSocket")
    
    # Send initial status
    try:
        ws.send(json.dumps({
            'event': 'connection_status', 
            'data': {'connected': arduino_server.connected}
        }))
        ws.send(json.dumps({
            'event': 'temperature_update',
            'data': {
                'temperature': arduino_server.temperature,
                'set_temperature': arduino_server.set_temperature
            }
        }))
        ws.send(json.dumps({
            'event': 'position_update',
            'data': arduino_server.position
        }))
        ws.send(json.dumps({
            'event': 'motor_states_update',
            'data': arduino_server.motor_states
        }))
        ws.send(json.dumps({
            'event': 'pneumatics_update',
            'data': arduino_server.pneumatics
        }))
        ws.send(json.dumps({
            'event': 'vacuums_update',
            'data': arduino_server.vacuums
        }))
        ws.send(json.dumps({
            'event': 'tape_update',
            'data': arduino_server.tape
        }))
    except Exception as e:
        logging.error(f"Error sending initial status: {e}")
    
    try:
        while True:
            message = ws.receive()
            if message is None:
                break
            
            try:
                data = json.loads(message)
                event = data.get('event')
                event_data = data.get('data', {})
                
                # Handle different events
                if event == 'get_arduino_status':
                    ws.send(json.dumps({
                        'event': 'arduino_connection_status',
                        'data': {'connected': arduino_server.connected}
                    }))
                
                elif event == 'send_command':
                    handle_command_ws(event_data, ws)
                
                elif event == 'move_position':
                    handle_move_position_ws(event_data, ws)
                
                elif event == 'enable_axis':
                    handle_enable_axis_ws(event_data, ws)
                
                elif event == 'set_temperature':
                    handle_temperature_ws(event_data, ws)
                
                elif event == 'pneumatic_control':
                    handle_pneumatic_ws(event_data, ws)
                
                elif event == 'vacuum_control':
                    handle_vacuum_ws(event_data, ws)
                
                elif event == 'disable_motor':
                    handle_disable_motor_ws(event_data, ws)
                
                elif event == 'emergency_stop':
                    handle_emergency_stop_ws()
                
                elif event == 'tape_motor':
                    handle_tape_motor_ws(event_data, ws)
                
                elif event == 'get_macros':
                    handle_get_macros_ws(ws)
                
                elif event == 'save_macro':
                    handle_save_macro_ws(event_data, ws)
                
                elif event == 'load_macro':
                    handle_load_macro_ws(event_data, ws)
                
                elif event == 'delete_macro':
                    handle_delete_macro_ws(event_data, ws)
                
                elif event == 'run_macro':
                    handle_run_macro_ws(event_data, ws)
                
                elif event == 'stop_macro':
                    handle_stop_macro_ws(ws)
                
            except json.JSONDecodeError as e:
                logging.error(f"Invalid JSON received: {message}")
            except Exception as e:
                logging.error(f"Error handling WebSocket message: {e}")
    
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        websocket_clients.discard(ws)
        logging.info("Client disconnected from WebSocket")

# WebSocket event handlers (similar to SocketIO handlers but adapted)
def handle_command_ws(data, ws):
    command = data.get('command', '')
    logging.info(f"Button Press: Raw command '{command}' received from web interface")
    
    if command:
        if arduino_server.connected:
            arduino_server.command_queue.put(command)
            logging.info(f"Button Press: Command '{command}' queued for Arduino")
            ws.send(json.dumps({
                'event': 'command_sent',
                'data': {'command': command, 'status': 'queued'}
            }))
        else:
            logging.warning(f"Button Press: Command '{command}' received but Arduino not connected")
            ws.send(json.dumps({
                'event': 'command_sent',
                'data': {'command': command, 'status': 'not_connected'}
            }))
    else:
        logging.warning("Button Press: Empty command received")

def handle_move_position_ws(data, ws):
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
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'queued'}
        }))
    else:
        logging.warning(f"Button Press: Move command '{command}' received but Arduino not connected")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'not_connected'}
        }))

def handle_enable_axis_ws(data, ws):
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
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'queued'}
        }))
    else:
        logging.warning(f"Button Press: Enable axis command '{command}' received but Arduino not connected")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'not_connected'}
        }))

def handle_temperature_ws(data, ws):
    temperature = data.get('temperature', 0)
    logging.info(f"Button Press: Set temperature to {temperature}°C")
    
    command = f"SetTemperature {temperature}"
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Temperature command '{command}' queued for Arduino")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'queued'}
        }))
    else:
        logging.warning(f"Button Press: Temperature command '{command}' received but Arduino not connected")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'not_connected'}
        }))

def handle_pneumatic_ws(data, ws):
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
            ws.send(json.dumps({
                'event': 'command_sent',
                'data': {'command': command, 'status': 'queued'}
            }))
        else:
            logging.warning(f"Button Press: Pneumatic command '{command}' received but Arduino not connected")
            ws.send(json.dumps({
                'event': 'command_sent',
                'data': {'command': command, 'status': 'not_connected'}
            }))
    else:
        logging.warning(f"Button Press: Invalid pneumatic command - component: {component}, action: {action}")

def handle_vacuum_ws(data, ws):
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
            ws.send(json.dumps({
                'event': 'command_sent',
                'data': {'command': command, 'status': 'queued'}
            }))
        else:
            logging.warning(f"Button Press: Vacuum command '{command}' received but Arduino not connected")
            ws.send(json.dumps({
                'event': 'command_sent',
                'data': {'command': command, 'status': 'not_connected'}
            }))
    else:
        logging.warning(f"Button Press: Invalid vacuum command - component: {component}, action: {action}")

def handle_disable_motor_ws(data, ws):
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
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'queued'}
        }))
    else:
        logging.warning(f"Button Press: Disable motor command '{command}' received but Arduino not connected")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'not_connected'}
        }))

def handle_emergency_stop_ws():
    logging.warning("Button Press: EMERGENCY STOP activated!")
    
    # Also stop any running macro
    if macro_executor.is_running:
        macro_executor.stop_macro()
    
    if arduino_server.connected:
        arduino_server.command_queue.put("STOP")
        logging.warning("Button Press: EMERGENCY STOP command queued for Arduino")
        broadcast_message('command_sent', {'command': 'STOP - EMERGENCY STOP', 'status': 'queued'})
    else:
        logging.warning("Button Press: EMERGENCY STOP requested but Arduino not connected")
        broadcast_message('command_sent', {'command': 'STOP - EMERGENCY STOP', 'status': 'not_connected'})

def handle_tape_motor_ws(data, ws):
    speed = data.get('speed', 0)
    torque = data.get('torque', 0)
    time_ms = data.get('time', 0)
    
    logging.info(f"Button Press: Tape motor - Speed: {speed}, Torque: {torque}, Time: {time_ms}ms")
    
    command = f"Tape {speed} {torque} {time_ms}"
    
    if arduino_server.connected:
        arduino_server.command_queue.put(command)
        logging.info(f"Button Press: Tape motor command '{command}' queued for Arduino")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'queued'}
        }))
    else:
        logging.warning(f"Button Press: Tape motor command '{command}' received but Arduino not connected")
        ws.send(json.dumps({
            'event': 'command_sent',
            'data': {'command': command, 'status': 'not_connected'}
        }))

# Macro-related WebSocket handlers
def handle_get_macros_ws(ws):
    """Get list of all saved macros"""
    logging.info("Getting list of macros")
    macros = macro_executor.list_macros()
    ws.send(json.dumps({
        'event': 'macro_list',
        'data': {'macros': macros}
    }))

def handle_save_macro_ws(data, ws):
    """Save a macro"""
    name = data.get('name', '').strip()
    content = data.get('content', '')
    variables = data.get('variables', {})
    
    if not name:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': 'Macro name is required'}
        }))
        return
    
    # Update variables if provided
    if variables:
        macro_executor.variables.update(
            variables.get('CHIP_X'),
            variables.get('CHIP_Y'),
            variables.get('STAGE_X')
        )
    
    if macro_executor.save_macro(name, content):
        logging.info(f"Macro saved: {name}")
        ws.send(json.dumps({
            'event': 'macro_created',
            'data': {'name': name}
        }))
    else:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': f'Failed to save macro {name}'}
        }))

def handle_load_macro_ws(data, ws):
    """Load macro content for editing"""
    name = data.get('name', '').strip()
    
    if not name:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': 'Macro name is required'}
        }))
        return
    
    content = macro_executor.load_macro(name)
    if content:
        ws.send(json.dumps({
            'event': 'macro_content',
            'data': {'name': name, 'content': content}
        }))
    else:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': f'Failed to load macro {name}'}
        }))

def handle_delete_macro_ws(data, ws):
    """Delete a macro"""
    name = data.get('name', '').strip()
    
    if not name:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': 'Macro name is required'}
        }))
        return
    
    if macro_executor.delete_macro(name):
        logging.info(f"Macro deleted: {name}")
        ws.send(json.dumps({
            'event': 'macro_deleted',
            'data': {'name': name}
        }))
    else:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': f'Failed to delete macro {name}'}
        }))

def handle_run_macro_ws(data, ws):
    """Run a macro"""
    name = data.get('name', '').strip()
    variables = data.get('variables', {})
    
    if not name:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': 'Macro name is required'}
        }))
        return
    
    if not arduino_server.connected:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': 'Arduino not connected'}
        }))
        return
    
    logging.info(f"Running macro: {name}")
    ws.send(json.dumps({
        'event': 'macro_executed',
        'data': {'name': name}
    }))
    macro_executor.execute_macro(name, variables)

def handle_stop_macro_ws(ws):
    """Stop currently running macro"""
    if macro_executor.stop_macro():
        logging.info("Macro execution stopped")
        ws.send(json.dumps({
            'event': 'macro_stopped',
            'data': {'success': True}
        }))
    else:
        ws.send(json.dumps({
            'event': 'macro_error',
            'data': {'error': 'No macro is currently running'}
        }))

# Web Routes
@app.route('/')
def index():
    return render_template('control.html')

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
    logging.info("Macro system enabled - macros will be saved to 'macros' directory")
    
    # Run the Flask app with Flask-Sock
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False)