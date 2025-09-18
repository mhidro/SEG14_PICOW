import machine
import asyncio
import utime

class ButtonPin(machine.Pin):
    """
    Custom Pin class for buttons, with optional value inversion.
    """
    def __init__(self, pin, mode, pull, *, inverted=False):
        super().__init__(pin, mode, pull) 
        self._inverted = inverted
    
    def value(self):
        """
        Returns the pin value, inverted if specified during initialization.
        """
        raw_value = super().value()
        return not raw_value if self._inverted else raw_value

class EdgeTriggerPin(ButtonPin):
    """
    Pin class with edge detection and callback support.
    Supports registering callbacks for rising and falling edges with optional debounce.
    Can use either polling or hardware interrupts for edge detection.
    """
    EDGE_RISING = 1
    EDGE_FALLING = 2
    EDGE_BOTH = 3
    
    def __init__(self, pin, mode, pull, *, inverted=False, debounce_ms=0, use_irq=False):
        super().__init__(pin, mode, pull, inverted=inverted)
        self._callbacks = {
            self.EDGE_RISING: [],
            self.EDGE_FALLING: []
        }
        # Allow brief settle time for initial state
        utime.sleep_ms(5)  # Brief delay to let pin stabilize
        self._last_value = self.value()
        self._debounce_ms = debounce_ms
        self._last_trigger_time = 0
        self._use_irq = use_irq
        self._latched_value = None
        
        # Setup IRQ if requested
        if use_irq:
            trigger = 0
            trigger |= machine.Pin.IRQ_RISING
            trigger |= machine.Pin.IRQ_FALLING
            self.irq(trigger=trigger, handler=self._irq_handler)
    
    def add_callback(self, edge_type, callback):
        """
        Register a callback function for the specified edge type.
        edge_type: EDGE_RISING, EDGE_FALLING, or EDGE_BOTH
        callback: function to call when edge is detected
        """
        if edge_type in (self.EDGE_RISING, self.EDGE_BOTH):
            self._callbacks[self.EDGE_RISING].append(callback)
        if edge_type in (self.EDGE_FALLING, self.EDGE_BOTH):
            self._callbacks[self.EDGE_FALLING].append(callback)
        return callback  # Return callback to allow use as decorator
    
    def remove_callback(self, callback):
        """
        Remove a callback function from all edge types.
        """
        self._callbacks[self.EDGE_RISING] = [cb for cb in self._callbacks[self.EDGE_RISING] if cb != callback]
        self._callbacks[self.EDGE_FALLING] = [cb for cb in self._callbacks[self.EDGE_FALLING] if cb != callback]
    
    def _irq_handler(self, pin):
        """
        IRQ handler - minimized to comply with MicroPython ISR rules.
        Latches current pin value and schedules for processing outside the ISR.
        """
        self._latched_value = self.value()  # Capture value at time of interrupt
        BoardIO.schedule_callback(self)
    
    def _poll_handler(self):
        """
        Handle edge detection and callbacks directly for polling mode.
        """
        current_value = self.value()
        if current_value != self._last_value:
            current_time = utime.ticks_ms()
            if self._debounce_ms == 0 or utime.ticks_diff(current_time, self._last_trigger_time) >= self._debounce_ms:
                edge_type = self.EDGE_RISING if current_value else self.EDGE_FALLING
                for callback in self._callbacks[edge_type]:
                    callback(self)
                self._last_trigger_time = current_time
                # Only update last_value after successful debounce check
                self._last_value = current_value

class PinGroup:
    """
    Represents a group of related pins (e.g., INPUT, OUTPUT, etc.)
    """
    def __init__(self, board_io, group_name):
        self._board_io = board_io
        self._group_name = group_name
        self._pins = {}
    
    def add_pin(self, name, pin):
        """Add a pin to this group"""
        self._pins[name] = pin
        
        # Register for polling if needed
        if isinstance(pin, EdgeTriggerPin) and not pin._use_irq:
            self._board_io.add_monitored_pin(pin)
        
        return pin
    
    def __getattr__(self, name):
        """Handle attribute access for pins in this group"""
        if name in self._pins:
            return self._pins[name]
        raise AttributeError(f"'{self._group_name}' group has no pin named '{name}'")
    
    def get_all_pins(self):
        """Return all pins in this group"""
        return self._pins.values()

class BoardIO:
    """
    Manages I/O pins with edge detection capabilities.
    Organizes pins into logical groups.
    """
    # Static set for callbacks from IRQs
    _pending_callbacks = set()
    
    @staticmethod
    def schedule_callback(pin):
        """Schedule a pin for processing outside ISR"""
        BoardIO._pending_callbacks.add(pin)
    
    @staticmethod
    def process_pending_callbacks():
        """Process any callbacks that were scheduled by IRQs"""
        pending = list(BoardIO._pending_callbacks)
        BoardIO._pending_callbacks.clear()
        
        for pin in pending:
            if pin._latched_value is not None:
                latched = pin._latched_value
                pin._latched_value = None
                
                current_value = pin.value()
                if current_value == latched and current_value != pin._last_value:
                    current_time = utime.ticks_ms()
                    if pin._debounce_ms == 0 or utime.ticks_diff(current_time, pin._last_trigger_time) >= pin._debounce_ms:
                        edge_type = pin.EDGE_RISING if current_value else pin.EDGE_FALLING
                        for callback in pin._callbacks[edge_type]:
                            callback(pin)
                        pin._last_trigger_time = current_time
                        pin._last_value = current_value
    
    def __init__(self):
        """Initialize an empty BoardIO instance with pin groups"""
        self._monitored_pins = []
        self._groups = {}
        
        # Create standard pin groups
        self.INPUT = self.create_group('INPUT')
        self.OUTPUT = self.create_group('OUTPUT')
        self.ANALOG = self.create_group('ANALOG')
        # Add more standard groups as needed
    
    def create_group(self, group_name):
        """Create a new pin group"""
        group = PinGroup(self, group_name)
        self._groups[group_name] = group
        return group
    
    def add_monitored_pin(self, pin):
        """Add a pin to the edge monitoring list (for polling mode)"""
        if pin not in self._monitored_pins and not pin._use_irq:
            self._monitored_pins.append(pin)
    
    def remove_monitored_pin(self, pin):
        """Remove a pin from the edge monitoring list"""
        if pin in self._monitored_pins:
            self._monitored_pins.remove(pin)
    
    async def monitor_edges(self):
        """Background task to monitor edges on all registered pins and process IRQ callbacks"""
        while True:
            # Process IRQ callbacks first
            BoardIO.process_pending_callbacks()
            
            # Handle polling pins directly
            for pin in self._monitored_pins:
                pin._poll_handler()
                    
            await asyncio.sleep_ms(10)  # Poll interval



