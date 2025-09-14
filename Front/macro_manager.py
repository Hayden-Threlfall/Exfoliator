import os
import re
import logging
import asyncio
import json
import threading

from utils import broadcast_message

# Directory to store macro files
MACROS_DIR = 'macros'

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

class MacroExecutor:
    """Class to handle macro execution"""
    def __init__(self, arduino_server):
        self.arduino_server = arduino_server
        self.variables = MacroVariables()
        self.is_running = False
        self.current_macro = None
        self.stop_requested = False
        self.websocket_clients = set()  # To be set by the main app

    def set_websocket_clients(self, clients):
        self.websocket_clients = clients

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
        line = line.strip()  # Skip comments and empty lines
        if not line or line.startswith('#'):
            return None, None
        
        # Check for delay command
        if line.lower().startswith('delay'):
            match = re.match(r'delay\s+(\d+)', line, re.IGNORECASE)
            if match:
                return 'delay', int(match.group(1))
        
        # Substitute variables in the command
        command = self.variables.substitute_variables(line)
        return 'command', command

    async def execute_macro_async(self, name, variables=None):
        """Execute macro asynchronously to avoid blocking"""
        if self.is_running:
            broadcast_message(self.websocket_clients, 'macro_error', {'error': 'Another macro is already running'})
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
                broadcast_message(self.websocket_clients, 'macro_error', {'error': f'Macro {name} not found'})
                return
            
            # Parse and execute commands
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if self.stop_requested:
                    logging.info(f"Macro {name} stopped by user")
                    broadcast_message(self.websocket_clients, 'macro_error', {'error': f'Macro {name} stopped'})
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
                broadcast_message(self.websocket_clients, 'macro_completed', {'name': name})

        except Exception as e:
            logging.error(f"Error executing macro {name}: {e}")
            broadcast_message(self.websocket_clients, 'macro_error', {'error': str(e)})

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