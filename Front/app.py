from flask import Flask, request, jsonify, render_template
from flask_sock import Sock
from flask_cors import CORS
import threading
import logging
import json
import os
import asyncio

from arduino_server import ArduinoTCPServer, arduino_communication_thread
from macro_manager import MacroExecutor, MacroVariables, MACROS_DIR
from websocket_handlers import setup_websocket_handlers, broadcast_message
from utils import parse_json_status

app = Flask(__name__)
app.config['SECRET_KEY'] = 'exfoliator-secure-key-2024'
CORS(app)
sock = Sock(app)

# Configuration
ARDUINO_HOST = '192.168.4.100'  # Arduino IP
TCP_SERVER_PORT = 1053  # TCP port to listen for Arduino
HTTP_PORT = 80  # HTTP port for Flask
HTTP_HOST = '192.168.3.80'  # Flask server IP
SERVER_HOST = '192.168.4.120'  # Raspberry Pi server IP for TCP

# Create macros directory if it doesn't exist
if not os.path.exists(MACROS_DIR):
    os.makedirs(MACROS_DIR)

# Global variable to store WebSocket connections
websocket_clients = set()

# Initialize core components
arduino_server = ArduinoTCPServer()
macro_executor = MacroExecutor(arduino_server)

# Set up WebSocket handlers
setup_websocket_handlers(app, sock, arduino_server, macro_executor, websocket_clients)

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
communication_thread = threading.Thread(target=arduino_communication_thread, args=(arduino_server, websocket_clients, parse_json_status, ), daemon=True)
communication_thread.start()

if __name__ == '__main__':
    # Setup logging with different levels for testing
    # logging.basicConfig(
    #     level=logging.INFO,  # Change to DEBUG for more verbose output
    #     format='%(asctime)s - %(levelname)s - %(message)s',
    #     handlers=[
    #         logging.StreamHandler(),
    #         logging.FileHandler('flask_app.log')
    #     ]
    # )
    # logging.info("Starting Flask application...")
    # logging.info(f"HTTP Server will run on port {HTTP_PORT}")
    # logging.info(f"TCP Server will listen on port {TCP_SERVER_PORT}")
    # logging.info("PING/PONG heartbeat system enabled - sending PING every 2 seconds")
    # logging.info("Macro system enabled - macros will be saved to 'macros' directory")
    
    # Run the Flask app with Flask-Sock
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False)