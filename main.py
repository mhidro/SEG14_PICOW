from boardio import BoardIO, EdgeTriggerPin, machine
import asyncio

# Create BoardIO instance
board_io = BoardIO()

# Initialize pins in main.py with groups
board_io.OUTPUT.add_pin('led', machine.Pin('LED', machine.Pin.OUT))

# Create a button with IRQ-based edge detection
board_io.INPUT.add_pin('button', EdgeTriggerPin(15, machine.Pin.IN, machine.Pin.PULL_UP, 
                       inverted=True, debounce_ms=50, use_irq=True))
                 
# Example of a button using polling-based edge detection
board_io.INPUT.add_pin('button2', EdgeTriggerPin(14, machine.Pin.IN, machine.Pin.PULL_UP,
                       inverted=True, debounce_ms=50, use_irq=False))

# Use a single variable for the current period instead of an index into a list
period_initial = 1000
current_period = period_initial


async def toggle_led(led_builtin, time_ms):
    """
    LED toggling task with support for special period values:
    - 0: LED always ON
    - -1: LED always OFF
    - Positive values: Normal blinking with that period
    """
    while True:
        # Handle special period values
        if time_ms == 0:
            # Always ON
            led_builtin.on()
        elif time_ms == -1:
            # Always OFF
            led_builtin.off()
        else:
            # Normal blinking
            led_builtin.toggle()

        await asyncio.sleep_ms(abs(time_ms) if time_ms != 0 else 50)  # Use absolute value, treat 0 as 50ms wait

async def main_loop():
    print("Entering main loop...")    
    task_handles = []  
    
    # Start edge monitoring task (this needs to run throughout)
    edge_monitor_task = asyncio.create_task(board_io.monitor_edges())
    task_handles.append(edge_monitor_task)
    
    # Initially start the LED toggling task with current period
    led_strobe_task = asyncio.create_task(toggle_led(board_io.OUTPUT.led, current_period))
    task_handles.append(led_strobe_task)
    blinker_running = True
    
    # Create an event for program termination
    stop_event = asyncio.Event()
    
    # Button press callback function to stop/start LED blinker
    def on_button_press(pin):
        nonlocal led_strobe_task, blinker_running, task_handles
        
        if blinker_running:
            # Stop the LED blinker task
            print("Stopping LED blinker")
            led_strobe_task.cancel()
            task_handles.remove(led_strobe_task)
            board_io.OUTPUT.led.off()  # Ensure LED is off when stopped
            blinker_running = False
        else:
            # Start a new LED blinker task with current period
            print(f"Starting LED blinker (period: {current_period}ms)")
            led_strobe_task = asyncio.create_task(toggle_led(board_io.OUTPUT.led, current_period))
            task_handles.append(led_strobe_task)
            blinker_running = True
    
    # Register button press callback
    board_io.INPUT.button.add_callback(EdgeTriggerPin.EDGE_RISING, on_button_press)
    
    # Button2 callback to cycle through blink periods with mathematical calculations
    def on_button2_press(pin):
        global current_period
        nonlocal led_strobe_task, blinker_running, task_handles
        
        # Calculate next period based on simple division
        if current_period == -1:
            # When LED is off, reset to initial period
            current_period = period_initial
        elif current_period == 0:
            # When LED is fully on, turn it off
            current_period = -1
        else:
            # Otherwise halve the period, rounding down
            current_period = current_period // 2
            ## If period becomes too small, set to always on
            if current_period < 7:  # Minimum threshold
                current_period = 0
        
        # Display the appropriate message based on period value
        if current_period == 0:
            print("Blink mode: Always ON")
        elif current_period == -1:
            print("Blink mode: Always OFF")
        else:
            print(f"Blink period changed to {current_period}ms")
        
        # If blinker is running, restart it with new period
        if blinker_running:
            # Stop the current task
            led_strobe_task.cancel()
            task_handles.remove(led_strobe_task)
            
            # Start a new task with the updated period
            led_strobe_task = asyncio.create_task(toggle_led(board_io.OUTPUT.led, current_period))
            task_handles.append(led_strobe_task)
    
    # Register button2 for period cycling
    board_io.INPUT.button2.add_callback(EdgeTriggerPin.EDGE_RISING, on_button2_press)

    try:
        # Wait indefinitely (until KeyboardInterrupt)
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        # Clean up all running tasks
        for task in task_handles:
            task.cancel()

        # Wait for tasks to acknowledge cancellation
        await asyncio.gather(*task_handles, return_exceptions=True)

if __name__ == "__main__":
    board_io.OUTPUT.led.on()
    print("Starting main loop...")
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass

    board_io.OUTPUT.led.off()
    print(f"Finished. Last blink period: {current_period}ms")