import json
import logging

def broadcast_message(websocket_clients, event, data):
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

def parse_json_status(websocket_clients, arduino_server, json_string):
    """Parse JSON status updates from Arduino"""
    try:
        logging.debug(f"Parsing JSON: {json_string}")
        data = json.loads(json_string)

        # Update position
        if 'x' in data and 'y' in data:
            arduino_server.position['x'] = float(data['x'])
            arduino_server.position['y'] = float(data['y'])
            broadcast_message(websocket_clients, 'position_update', arduino_server.position)
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
            broadcast_message(websocket_clients, 'motor_states_update', arduino_server.motor_states)
            logging.debug(f"Motor states update: {arduino_server.motor_states}")

        # Update tape motor status
        if 'tape' in data:
            tape_data = data['tape']
            if isinstance(tape_data, list) and len(tape_data) >= 2:
                arduino_server.tape['speed'] = int(tape_data[0])
                arduino_server.tape['torque'] = int(tape_data[1])
                broadcast_message(websocket_clients, 'tape_update', arduino_server.tape)
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
            broadcast_message(websocket_clients, 'pneumatics_update', arduino_server.pneumatics)
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
            broadcast_message(websocket_clients, 'vacuums_update', arduino_server.vacuums)
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
            broadcast_message(websocket_clients, 'temperature_update', {
                'temperature': arduino_server.temperature,
                'set_temperature': arduino_server.set_temperature
            })
            logging.debug(f"Temperature update: {arduino_server.temperature}°C (target: {arduino_server.set_temperature}°C)")

        # Update emergency stop status
        if 'eStopTriggered' in data:
            arduino_server.estop_triggered = bool(data['eStopTriggered'])
            broadcast_message(websocket_clients, 'estop_update', {'triggered': arduino_server.estop_triggered})
            if arduino_server.estop_triggered:
                logging.warning("Emergency stop triggered!")

    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON status: {json_string} - Error: {e}")
    except Exception as e:
        logging.error(f"Error processing JSON status: {e}")