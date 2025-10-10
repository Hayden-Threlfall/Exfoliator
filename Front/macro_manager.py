import os
import re
import logging
import asyncio
import json
import threading

from utils import broadcast_message

# Directory to store macro files
MACROS_DIR = 'macros'
CONFIG_FILE = os.path.join(MACROS_DIR, 'variables.json')

class MacroVariables:
    """Class to hold and manage macro position variables"""
    def __init__(self):
        # Default values
        self.X_AXIS_INITIAL_CHIPWELL = 105
        self.Y_AXIS_INITIAL_CHIPWELL = 64.65
        self.X_AXIS_VACUUM_CHUCK_POSITION = 8

        # User-definable values
        self.CHIP_X = self.X_AXIS_INITIAL_CHIPWELL
        self.CHIP_Y = self.Y_AXIS_INITIAL_CHIPWELL
        self.STAGE_X = self.X_AXIS_VACUUM_CHUCK_POSITION
        
        # Load saved values if they exist
        self.load_from_file()

    def load_from_file(self):
        """Load variables from config file"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.CHIP_X = float(data.get('CHIP_X', self.CHIP_X))
                    self.CHIP_Y = float(data.get('CHIP_Y', self.CHIP_Y))
                    self.STAGE_X = float(data.get('STAGE_X', self.STAGE_X))
                    logging.info(f"Loaded macro variables from file: {self.get_variables()}")
        except Exception as e:
            logging.error(f"Failed to load macro variables: {e}")

    def save_to_file(self):
        """Save variables to config file"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.get_variables(), f, indent=2)
            logging.info(f"Saved macro variables to file: {self.get_variables()}")
            return True
        except Exception as e:
            logging.error(f"Failed to save macro variables: {e}")
            return False

    def update(self, chip_x=None, chip_y=None, stage_x=None):
        """Update variables with provided values and save to file"""
        if chip_x is not None:
            self.CHIP_X = float(chip_x)
        if chip_y is not None:
            self.CHIP_Y = float(chip_y)
        if stage_x is not None:
            self.STAGE_X = float(stage_x)
        
        # Save to file whenever values are updated
        self.save_to_file()

    def get_variables(self):
        """Get current variable values as dictionary"""
        return {
            'CHIP_X': self.CHIP_X,
            'CHIP_Y': self.CHIP_Y,
            'STAGE_X': self.STAGE_X
        }

    def substitute_variables(self, command):
        """Replace variables in command with their values and evaluate expressions"""
        # First, substitute variable names with their values
        temp_command = command.replace('CHIP_X', str(self.CHIP_X))
        temp_command = temp_command.replace('CHIP_Y', str(self.CHIP_Y))
        temp_command = temp_command.replace('STAGE_X', str(self.STAGE_X))
        
        # Find and evaluate math expressions (e.g., "MoveX 105 + 1.2")
        # Pattern: number followed by operator and number
        pattern = r'(-?\d+\.?\d*)\s*([+\-*/])\s*(-?\d+\.?\d*)'
        
        def eval_match(match):
            left = float(match.group(1))
            operator = match.group(2)
            right = float(match.group(3))
            
            if operator == '+':
                result = left + right
            elif operator == '-':
                result = left - right
            elif operator == '*':
                result = left * right
            elif operator == '/':
                result = left / right if right != 0 else left
            
            return str(result)
        
        # Replace all math expressions with their results
        while re.search(pattern, temp_command):
            temp_command = re.sub(pattern, eval_match, temp_command)
        
        return temp_command

class MacroExecutor:
    """Class to handle macro execution"""
    def __init__(self, arduino_server):
        self.arduino_server = arduino_server
        self.variables = MacroVariables()
        self.is_running = False
        self.current_macro = None
        self.stop_requested = False
        self.websocket_clients = set()  # To be set by the main app
        self.completion_event = threading.Event()  # Event to signal macro completion

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
        line = line.strip()
        if not line or line.startswith('#'):
            return None, None
        
        # Check for delay command
        if line.lower().startswith('delay'):
            match = re.match(r'delay\s+(\d+)', line, re.IGNORECASE)
            if match:
                return 'delay', int(match.group(1))
        
        # CHANGE THIS: Accept both "macro" and "Macro" (case-insensitive)
        if line.lower().startswith('macro'):
            match = re.match(r'macro\s+(\S+)', line, re.IGNORECASE)
            if match:
                macro_name = match.group(1)
                return 'macro', macro_name
        
        # Substitute variables in the command
        command = self.variables.substitute_variables(line)
        return 'command', command

    async def execute_macro_async(self, name, variables=None):
        """Execute macro asynchronously to avoid blocking"""
        if self.is_running:
            broadcast_message(self.websocket_clients, 'macro_error', {'error': 'Another macro is already running'})
            self.completion_event.set()
            return

        self.is_running = True
        self.current_macro = name
        self.stop_requested = False
        self.completion_event.clear()

        # SAVE current variables to restore after execution
        saved_vars = {
            'CHIP_X': self.variables.CHIP_X,
            'CHIP_Y': self.variables.CHIP_Y,
            'STAGE_X': self.variables.STAGE_X
        }

        try:
            # TEMPORARILY set variables for this execution (don't save to file)
            if variables:
                self.variables.CHIP_X = float(variables.get('CHIP_X', self.variables.CHIP_X))
                self.variables.CHIP_Y = float(variables.get('CHIP_Y', self.variables.CHIP_Y))
                self.variables.STAGE_X = float(variables.get('STAGE_X', self.variables.STAGE_X))
                logging.info(f"Temporarily using CHIP_X={self.variables.CHIP_X}, CHIP_Y={self.variables.CHIP_Y}, STAGE_X={self.variables.STAGE_X}")
            
            # Load macro content
            content = self.load_macro(name)
            if not content:
                broadcast_message(self.websocket_clients, 'macro_error', {'error': f'Macro {name} not found'})
                self.completion_event.set()
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
                    await asyncio.sleep(0.1)
                elif cmd_type == 'macro':
                    logging.info(f"Macro {name}: Executing nested macro {cmd_data}")
                    await self.execute_macro_async(cmd_data, None)

            if not self.stop_requested:
                logging.info(f"Macro {name} completed successfully")
                broadcast_message(self.websocket_clients, 'macro_completed', {'name': name})
                self.completion_event.set()

        except Exception as e:
            logging.error(f"Error executing macro {name}: {e}")
            broadcast_message(self.websocket_clients, 'macro_error', {'error': str(e)})
            self.completion_event.set()

        finally:
            # RESTORE original variables (don't save)
            self.variables.CHIP_X = saved_vars['CHIP_X']
            self.variables.CHIP_Y = saved_vars['CHIP_Y']
            self.variables.STAGE_X = saved_vars['STAGE_X']
            
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