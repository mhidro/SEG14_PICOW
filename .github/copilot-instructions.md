# SEG14_PICOW Development Guide

This guide provides key information for AI agents working with the SEG14_PICOW codebase, a MicroPython project for the Raspberry Pi Pico W microcontroller.

## Project Architecture

### Core Components

1. `boardio.py`: Core I/O abstraction layer
   - `BoardIO`: Main class for managing all I/O operations
   - `PinGroup`: Organizes pins into logical groups (INPUT, OUTPUT, ANALOG)
   - `ButtonPin`: Base class for input pins with value inversion support
   - `EdgeTriggerPin`: Advanced button handling with edge detection and callbacks

2. `main.py`: Application logic and entry point
   - Implements LED control and button interaction patterns
   - Uses asyncio for concurrent operation management
   - Demonstrates the event-driven programming model

### Key Design Patterns

1. **Pin Management Hierarchy**:
   ```python
   board_io = BoardIO()
   board_io.OUTPUT.add_pin('led', machine.Pin('LED', machine.Pin.OUT))
   board_io.INPUT.add_pin('button', EdgeTriggerPin(...))
   ```

2. **Edge Detection Options**:
   - IRQ-based (interrupt-driven): `use_irq=True`
   - Polling-based: `use_irq=False`
   Example:
   ```python
   # IRQ-based
   button = EdgeTriggerPin(15, machine.Pin.IN, machine.Pin.PULL_UP, use_irq=True)
   # Polling-based
   button2 = EdgeTriggerPin(14, machine.Pin.IN, machine.Pin.PULL_UP, use_irq=False)
   ```

3. **Event-Driven Callbacks**:
   ```python
   # Register callback for rising edge
   button.add_callback(EdgeTriggerPin.EDGE_RISING, on_button_press)
   ```

## Development Workflows

### Environment Setup

1. Required VS Code extensions (defined in `.vscode/extensions.json`):
   - ms-python.python
   - visualstudioexptteam.vscodeintellicode
   - ms-python.vscode-pylance
   - paulober.pico-w-go

2. MicroPython stubs are configured in `.vscode/settings.json`

### Code Style and Restrictions

1. **Unicode Restrictions**:
   - NO Unicode characters allowed in source code files
   - Use only ASCII characters (0-127) in all source files
   - This includes:
     - No Unicode symbols or emojis
     - No extended ASCII characters
     - No Unicode variable names
     - No Unicode string literals
   - Rationale: Ensures maximum compatibility with MicroPython and embedded systems

2. **String Guidelines**:
   - Use only standard ASCII strings
   - For special characters, use ASCII escape sequences
   - Example: Use '\n' instead of line-ending Unicode characters

### Testing and Debugging

1. Use the MicroPico vREPL terminal for interactive testing
2. LED states indicate program status:
   - ON at startup
   - OFF at shutdown
   - Blinking during normal operation

### Common Patterns

1. **Pin Configuration**:
   - Group pins logically (INPUT, OUTPUT, ANALOG)
   - Use meaningful pin names
   - Configure with appropriate modes and pull resistors

2. **Asynchronous Operations**:
   - Always use `async/await` for time-dependent operations
   - Handle task cancellation in cleanup
   - Use `asyncio.create_task()` for concurrent operations

3. **Button Handling**:
   - Include debounce settings where needed
   - Prefer IRQ-based detection for critical inputs
   - Use polling for non-critical or high-frequency changes