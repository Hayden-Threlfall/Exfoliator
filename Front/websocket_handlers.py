import json
import logging
from utils import broadcast_message

def setup_websocket_handlers(app, sock, arduino_server, macro_executor, websocket_clients):
    """
    Sets up the WebSocket route and its handlers.
    This function acts as a centralized point for all WebSocket interactions.
    """
    macro_executor.set_websocket_clients(websocket_clients)

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
                        handle_command_ws(event_data, ws, arduino_server)
                    elif event == 'move_position':
                        handle_move_position_ws(event_data, ws, arduino_server)
                    elif event == 'enable_axis':
                        handle_enable_axis_ws(event_data, ws, arduino_server)
                    elif event == 'set_temperature':
                        handle_temperature_ws(event_data, ws, arduino_server)
                    elif event == 'pneumatic_control':
                        handle_pneumatic_ws(event_data, ws, arduino_server)
                    elif event == 'vacuum_control':
                        handle_vacuum_ws(event_data, ws, arduino_server)
                    elif event == 'disable_motor':
                        handle_disable_motor_ws(event_data, ws, arduino_server)
                    elif event == 'emergency_stop':
                        handle_emergency_stop_ws(arduino_server, macro_executor, websocket_clients)
                    elif event == 'tape_motor':
                        handle_tape_motor_ws(event_data, ws, arduino_server)
                    elif event == 'get_macros':
                        handle_get_macros_ws(ws, macro_executor)
                    elif event == 'save_macro':
                        handle_save_macro_ws(event_data, ws, macro_executor)
                    elif event == 'load_macro':
                        handle_load_macro_ws(event_data, ws, macro_executor)
                    elif event == 'delete_macro':
                        handle_delete_macro_ws(event_data, ws, macro_executor)
                    elif event == 'run_macro':
                        handle_run_macro_ws(event_data, ws, arduino_server, macro_executor)
                    elif event == 'stop_macro':
                        handle_stop_macro_ws(ws, macro_executor)

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
def handle_command_ws(data, ws, arduino_server):
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

def handle_move_position_ws(data, ws, arduino_server):
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

def handle_enable_axis_ws(data, ws, arduino_server):
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

def handle_temperature_ws(data, ws, arduino_server):
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

def handle_pneumatic_ws(data, ws, arduino_server):
    component = data.get('component')  # 'nozzle', 'stage', 'stamp'
    action = data.get('action')  # 'extend', 'retract'
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

def handle_vacuum_ws(data, ws, arduino_server):
    component = data.get('component')  # 'vacnozzle', 'chuck'
    action = data.get('action')  # 'on', 'off'
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

def handle_disable_motor_ws(data, ws, arduino_server):
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

def handle_emergency_stop_ws(arduino_server, macro_executor, websocket_clients):
    logging.warning("Button Press: EMERGENCY STOP activated!")
    # Also stop any running macro
    if macro_executor.is_running:
        macro_executor.stop_macro()

    if arduino_server.connected:
        arduino_server.command_queue.put("STOP")
        logging.warning("Button Press: EMERGENCY STOP command queued for Arduino")
        broadcast_message(websocket_clients, 'command_sent', {'command': 'STOP - EMERGENCY STOP', 'status': 'queued'})
    else:
        logging.warning("Button Press: EMERGENCY STOP requested but Arduino not connected")
        broadcast_message(websocket_clients, 'command_sent', {'command': 'STOP - EMERGENCY STOP', 'status': 'not_connected'})

def handle_tape_motor_ws(data, ws, arduino_server):
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
def handle_get_macros_ws(ws, macro_executor):
    """Get list of all saved macros"""
    logging.info("Getting list of macros")
    macros = macro_executor.list_macros()
    ws.send(json.dumps({
        'event': 'macro_list',
        'data': {'macros': macros}
    }))

def handle_save_macro_ws(data, ws, macro_executor):
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

def handle_load_macro_ws(data, ws, macro_executor):
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

def handle_delete_macro_ws(data, ws, macro_executor):
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

def handle_run_macro_ws(data, ws, arduino_server, macro_executor):
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

def handle_stop_macro_ws(ws, macro_executor):
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