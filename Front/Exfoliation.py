import asyncio
import logging
from typing import Optional, Dict, Any

class Exfoliation:
    def __init__(self, command_callback=None):
        """Simple exfoliation simulator for single chip processing"""
        
        # Position constants - only what we need
        self.X_AXIS_INITIAL_CHIPWELL = 105.5
        self.Y_AXIS_INITIAL_CHIPWELL = 4.5
        self.X_AXIS_VACUUM_CHUCK_POSITION = 8
        self.CHIP_DISTANCE = 12.5

        # Command callback
        self.command_callback = command_callback
        
        # Simple control flag
        self.running = False
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger('Exfoliation')

    def send_command(self, command: str, *args):
        """Send a command to the external system"""
        if self.command_callback:
            if args:
                full_command = f"{command} {' '.join(map(str, args))}"
            else:
                full_command = command
            self.command_callback(full_command)
            self.logger.info(f"Command: {full_command}")
        else:
            if args:
                self.logger.info(f"Command: {command} {' '.join(map(str, args))}")
            else:
                self.logger.info(f"Command: {command}")

    async def process_single_chip(self, chip_x: float, chip_y: float):
        """Process a single chip through complete exfoliation"""
        
        self.running = True
        self.logger.info(f"Starting chip processing at ({chip_x}, {chip_y})")
        
        # Initial setup
        self.send_command("SetTemperature", 40)
        self.send_command("Tape", 0, 4, 0)  # Initial tape torque
        await asyncio.sleep(0.5)
        
        # Move above chip in tray
        self.logger.info("Moving above chip in tray")
        self.send_command("VacNozzleOff")
        self.send_command("MoveX", chip_x)
        self.send_command("MoveY", chip_y)
        await asyncio.sleep(1.0)
        
        # Pick up chip from tray
        self.logger.info("Picking up chip from tray")
        self.send_command("ExtendNozzle")
        await asyncio.sleep(1.0)
        
        self.send_command("VacNozzleOn")
        await asyncio.sleep(1.0)
        
        self.send_command("RetractNozzle")
        await asyncio.sleep(0.25)
        
        # Move above chuck
        self.logger.info("Moving above chuck")
        self.send_command("MoveX", self.X_AXIS_VACUUM_CHUCK_POSITION)
        self.send_command("MoveY", chip_y)
        await asyncio.sleep(1.0)
        
        # Place chip on chuck
        self.logger.info("Placing chip on chuck")
        self.send_command("ExtendNozzle")
        await asyncio.sleep(1.5)
        
        self.send_command("ChuckOn")
        self.send_command("VacNozzleOff")
        await asyncio.sleep(0.5)
        
        self.send_command("RetractNozzle")
        await asyncio.sleep(0.5)
        
        # Stamp procedure
        self.logger.info("Starting stamp procedure")
        await self.stamp_procedure()
        
        # Pick up chip from chuck
        self.logger.info("Picking up chip from chuck")
        self.send_command("ExtendNozzle")
        await asyncio.sleep(0.5)
        
        self.send_command("VacNozzleOn")
        self.send_command("ChuckOff")
        await asyncio.sleep(0.5)
        
        self.send_command("RetractNozzle")
        await asyncio.sleep(0.25)
        
        # Move back to tray
        self.logger.info("Moving back to tray")
        self.send_command("MoveX", chip_x)
        self.send_command("MoveY", chip_y)
        await asyncio.sleep(1.0)
        
        # Place chip back on tray
        self.logger.info("Placing chip back on tray")
        self.send_command("ExtendNozzle")
        await asyncio.sleep(1.0)
        
        self.send_command("VacNozzleOff")
        await asyncio.sleep(1.0)
        
        self.send_command("RetractNozzle")
        
        # Cleanup
        self.send_command("SetTemperature", 30)
        self.running = False
        
        self.logger.info("Chip processing complete")

    async def stamp_procedure(self):
        """Execute the stamping/exfoliation procedure"""
        
        # Initial stamp
        self.send_command("ExtendStamp")
        self.send_command("Tape", 0, 1, 0)
        await asyncio.sleep(1.0)
        
        # First cycle
        self.send_command("RetractStamp")
        self.send_command("Tape", 0, 4, 0)
        await asyncio.sleep(1.0)
        
        self.send_command("ExtendStamp")
        self.send_command("Tape", 0, 1, 0)
        await asyncio.sleep(1.0)
        
        # Second cycle
        self.send_command("RetractStamp")
        self.send_command("Tape", 0, 4, 0)
        await asyncio.sleep(1.0)
        
        self.send_command("ExtendStamp")
        self.send_command("Tape", 0, 2, 0)
        await asyncio.sleep(1.0)
        
        # Chuck operations
        self.send_command("Tape", 0, 0, 0)
        self.send_command("RetractChipStage")
        await asyncio.sleep(1.0)
        
        self.send_command("RetractStamp")
        self.send_command("Tape", 0, 1, 0)
        await asyncio.sleep(1.0)
        
        self.send_command("ExtendStamp")
        await asyncio.sleep(1.0)
        
        # Main exfoliation sequence
        self.send_command("ExtendChipStage")
        self.send_command("Tape", 0, 5, 0)
        await asyncio.sleep(1.0)
        
        self.send_command("Tape", 0, 4, 0)
        await asyncio.sleep(1.0)
        
        self.send_command("Tape", 0, 2, 0)
        await asyncio.sleep(1.0)
        
        # High speed operation
        self.send_command("Tape", 4, 15, 0)
        await asyncio.sleep(1.0)
        
        self.send_command("Tape", 0, 2, 0)
        await asyncio.sleep(1.0)
        
        # Stop
        self.send_command("Tape", 0, 0, 0)

def example_command_callback(command: str):
    """Example callback function"""
    print(f"[COMMAND] {command}")

async def main():
    """Example usage"""
    exfoliate = Exfoliation(command_callback=example_command_callback)
    
    chipx = X_AXIS_INITIAL_CHIPWELL + exfoliationList[0][0] * CHIP_DISTANCE
    chipy = Y_AXIS_INITIAL_CHIPWELL + exfoliationList[0][1] * CHIP_DISTANCE
    await exfoliate.process_single_chip(chipx , chipy)

if __name__ == "__main__":
    asyncio.run(main())