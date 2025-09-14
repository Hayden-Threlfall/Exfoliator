import socket
import threading
import time
import queue
import logging
import json

from utils import parse_json_status, broadcast_message

# Configuration from main app
SERVER_HOST = '192.168.4.120'
TCP_SERVER_PORT = 1053

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
            # We don't have websocket_clients here, so we'll pass the message up to the main loop to broadcast
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
        # We don't have websocket_clients here, so we'll pass the message up to the main loop to broadcast

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
            # We don't have websocket_clients here, so we'll pass the message up to the main loop to broadcast
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
                # We don't have websocket_clients here, so we'll pass the message up to the main loop to broadcast
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

def arduino_communication_thread(arduino_server, websocket_clients, parse_json_status):
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
                broadcast_message(websocket_clients, 'arduino_connection_status', {'connected': True})

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
                            parse_json_status(websocket_clients, arduino_server, response)
                        elif response == "PONG":
                            logging.debug("PONG received")
                            # PONG response already updated last_response_received in read_response()
                        else:
                            broadcast_message(websocket_clients, 'machine_response', {'response': response})
                            logging.info(f"Arduino response: {response}")

            # Check connection health
            if arduino_server.connected:
                if not arduino_server.check_connection_health():
                    logging.warning("Connection health check failed - Arduino disconnected")
                    broadcast_message(websocket_clients, 'arduino_connection_status', {'connected': False})
                    continue

            # Read any incoming responses (JSON, PONG, etc.)
            response = arduino_server.read_response()
            if response:
                if response.startswith('{') and response.endswith('}'):
                    parse_json_status(websocket_clients, arduino_server, response)
                elif response == "PONG":
                    logging.debug("PONG received")
                    # Response timestamp already updated in read_response()
                else:
                    broadcast_message(websocket_clients, 'machine_response', {'response': response})
                    logging.info(f"Arduino response: {response}")

            time.sleep(0.1)  # Check frequently for responses
        except Exception as e:
            logging.error(f"Communication thread error: {e}")
            arduino_server.connected = False
            broadcast_message(websocket_clients, 'arduino_connection_status', {'connected': False})
            time.sleep(1)