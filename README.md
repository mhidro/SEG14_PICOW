# SEG14_PICOW

A MicroPython project for the Raspberry Pi Pico W microcontroller, implementing efficient I/O management and event-driven programming patterns.

## Overview

This project provides a structured approach to managing I/O operations on the Raspberry Pi Pico W using MicroPython. It features a robust pin management system with support for edge detection and event-driven programming.

## Features

- Organized I/O pin management through the `BoardIO` class
- Logical pin grouping (INPUT, OUTPUT, ANALOG)
- Advanced button handling with edge detection
- Event-driven programming with callback support
- Asynchronous operation management using `asyncio`

## Project Structure

- `boardio.py` - Core I/O abstraction layer
  - Contains `BoardIO`, `PinGroup`, `ButtonPin`, and `EdgeTriggerPin` classes
  - Handles pin management and event detection
- `main.py` - Application entry point
  - Implements LED control patterns
  - Manages button interactions
  - Coordinates asynchronous operations

## Setup

1. Install required VS Code extensions:
   - ms-python.python
   - visualstudioexptteam.vscodeintellicode
   - ms-python.vscode-pylance
   - paulober.pico-w-go

2. Connect your Raspberry Pi Pico W
3. Upload the project files to the device

## Usage

### Basic Pin Configuration

```python
board_io = BoardIO()
board_io.OUTPUT.add_pin('led', machine.Pin('LED', machine.Pin.OUT))
board_io.INPUT.add_pin('button', EdgeTriggerPin(15, machine.Pin.IN, machine.Pin.PULL_UP))
```

### Edge Detection Setup

```python
# IRQ-based (interrupt-driven)
button = EdgeTriggerPin(15, machine.Pin.IN, machine.Pin.PULL_UP, use_irq=True)

# Polling-based
button2 = EdgeTriggerPin(14, machine.Pin.IN, machine.Pin.PULL_UP, use_irq=False)
```

### Event Callbacks

```python
def on_button_press():
    print("Button pressed!")

button.add_callback(EdgeTriggerPin.EDGE_RISING, on_button_press)
```

## Development Guidelines

1. Use MicroPico vREPL terminal for interactive testing
2. Follow LED state indicators:
   - ON: startup
   - OFF: shutdown
   - Blinking: normal operation
3. Always use `async/await` for time-dependent operations
4. Handle task cancellation in cleanup routines
