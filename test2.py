import network
import uasyncio as asyncio
from machine import Pin
import time

# Import the web framework (contents of web.txt)
import uasyncio as asyncio
from hashlib import sha1
from binascii import b2a_base64
import struct

def unquote_plus(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        i += 1
        if c == '+':
            out.append(' ')
        elif c == '%':
            out.append(chr(int(s[i:i + 2], 16)))
            i += 2
        else:
            out.append(c)
    return ''.join(out)

def parse_qs(s):
    out = {}
    for x in s.split('&'):
        kv = x.split('=', 1)
        key = unquote_plus(kv[0])
        kv[0] = key
        if len(kv) == 1:
            val = True
            kv.append(val)
        else:
            val = unquote_plus(kv[1])
            kv[1] = val
        tmp = out.get(key, None)
        if tmp is None:
            out[key] = val
        else:
            if isinstance(tmp, list):
                tmp.append(val)
            else:
                out[key] = [tmp, val]
    return out

async def _parse_request(r, w):
    line = await r.readline()
    if not line:
        raise ValueError
    parts = line.decode().split()
    if len(parts) < 3:
        raise ValueError
    r.method = parts[0]
    r.path = parts[1]
    parts = r.path.split('?', 1)
    if len(parts) < 2:
        r.query = None
    else:
        r.path = parts[0]
        r.query = parts[1]
    r.headers = await _parse_headers(r)

async def _parse_headers(r):
    headers = {}
    while True:
        line = await r.readline()
        if not line:
            break
        line = line.decode()
        if line == '\r\n':
            break
        key, value = line.split(':', 1)
        headers[key.lower()] = value.strip()
    return headers

class App:
    def __init__(self, host='0.0.0.0', port=80):
        self.host = host
        self.port = port
        self.handlers = []

    def route(self, path, methods=['GET']):
        def wrapper(handler):
            self.handlers.append((path, methods, handler))
            return handler
        return wrapper

    async def _dispatch(self, r, w):
        try:
            await _parse_request(r, w)
        except:
            await w.wait_closed()
            return
        for path, methods, handler in self.handlers:
            if r.path != path:
                continue
            if r.method not in methods:
                continue
            await handler(r, w)
            await w.wait_closed()
            return
        await w.awrite(b'HTTP/1.0 404 Not Found\r\n\r\nNot Found')
        await w.wait_closed()

    async def serve(self):
        await asyncio.start_server(self._dispatch, self.host, self.port)

class WebSocket:
    HANDSHAKE_KEY = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    OP_TYPES = {
        0x0: 'cont',
        0x1: 'text',
        0x2: 'bytes',
        0x8: 'close',
        0x9: 'ping',
        0xa: 'pong',
    }

    @classmethod
    async def upgrade(cls, r, w):
        key = r.headers['sec-websocket-key'].encode()
        key += WebSocket.HANDSHAKE_KEY
        x = b2a_base64(sha1(key).digest()).strip()
        w.write(b'HTTP/1.1 101 Switching Protocols\r\n')
        w.write(b'Upgrade: websocket\r\n')
        w.write(b'Connection: Upgrade\r\n')
        w.write(b'Sec-WebSocket-Accept: ' + x + b'\r\n')
        w.write(b'\r\n')
        await w.drain()
        return cls(r, w)

    def __init__(self, r, w):
        self.r = r
        self.w = w

    async def recv(self):
        r = self.r
        x = await r.read(2)
        if not x or len(x) < 2:
            return None
        out = {}
        op, n = struct.unpack('!BB', x)
        out['fin'] = bool(op & (1 << 7))
        op = op & 0x0f
        if op not in WebSocket.OP_TYPES:
            raise None
        out['type'] = WebSocket.OP_TYPES[op]
        masked = bool(n & (1 << 7))
        n = n & 0x7f
        if n == 126:
            n, = struct.unpack('!H', await r.read(2))
        elif n == 127:
            n, = struct.unpack('!Q', await r.read(8))
        if masked:
            mask = await r.read(4)
        data = await r.read(n)
        if masked:
            data = bytearray(data)
            for i in range(len(data)):
                data[i] ^= mask[i % 4]
            data = bytes(data)
        if out['type'] == 'text':
            data = data.decode()
        out['data'] = data
        return out

    async def send(self, msg):
        if isinstance(msg, str):
            await self._send_op(0x1, msg.encode())
        elif isinstance(msg, bytes):
            await self._send_op(0x2, msg)

    async def _send_op(self, opcode, payload):
        w = self.w
        w.write(bytes([0x80 | opcode]))
        n = len(payload)
        if n < 126:
            w.write(bytes([n]))
        elif n < 65536:
            w.write(struct.pack('!BH', 126, n))
        else:
            w.write(struct.pack('!BQ', 127, n))
        w.write(payload)
        await w.drain()

class EventSource:
    @classmethod
    async def upgrade(cls, r, w):
        w.write(b'HTTP/1.0 200 OK\r\n')
        w.write(b'Content-Type: text/event-stream\r\n')
        w.write(b'Cache-Control: no-cache\r\n')
        w.write(b'Connection: keep-alive\r\n')
        w.write(b'Access-Control-Allow-Origin: *\r\n')
        w.write(b'\r\n')
        await w.drain()
        return cls(r, w)

    def __init__(self, r, w):
        self.r = r
        self.w = w

    async def send(self, msg, id=None, event=None):
        w = self.w
        if id is not None:
            w.write(b'id: {}\r\n'.format(id))
        if event is not None:
            w.write(b'event: {}\r\n'.format(event))
        w.write(b'data: {}\r\n'.format(msg))
        w.write(b'\r\n')
        await w.drain()

# --- Main Hydraulic Press Control System ---

# Access point credentials
AP_SSID = 'Presa_Control'
AP_PASSWORD = 'presa123'

# Initialize web app
app = App(host='0.0.0.0', port=80)

# --- Hardware Pin Configuration ---

# Output Relays (Pin numbers from README)
RELAY_MOTOR = Pin(13, Pin.OUT)      # Relay 1: Motor-Pump
RELAY_DOOR = Pin(12, Pin.OUT)       # Relay 2: Automatic Door
RELAY_12MB1 = Pin(28, Pin.OUT)      # Relay 3: Fast Down / Slow Down High Force
RELAY_12MB2 = Pin(27, Pin.OUT)      # Relay 4: Move Up
RELAY_13MB1 = Pin(26, Pin.OUT)      # Relay 5: Slow Down High Force
RELAY_13MB2 = Pin(19, Pin.OUT)      # Relay 6: Move Up
RELAY_RESERVE1 = Pin(17, Pin.OUT)   # Relay 7: Reserve
RELAY_RESERVE2 = Pin(16, Pin.OUT)   # Relay 8: Reserve

# Input Signals (Default Pull-up, configurable)
# We'll store the configuration in a dictionary
input_config = {
    'start_btn': {'pin': Pin(18, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'manual_up_btn': {'pin': Pin(20, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'manual_down_btn': {'pin': Pin(21, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'emergency_stop_btn': {'pin': Pin(22, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'press_top_sensor': {'pin': Pin(3, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'press_bottom_sensor': {'pin': Pin(4, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'door_open_sensor': {'pin': Pin(5, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    # Reserve inputs
    'reserve1': {'pin': Pin(6, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'reserve2': {'pin': Pin(7, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'reserve3': {'pin': Pin(8, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'reserve4': {'pin': Pin(14, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
    'reserve5': {'pin': Pin(15, Pin.IN, Pin.PULL_UP), 'pull': 'up'},
}

# Status LED
STATUS_LED = Pin(25, Pin.OUT)

# 7-Segment Display (Common Cathode)
DATA_PIN = Pin(11, Pin.OUT)
CLOCK_PIN = Pin(10, Pin.OUT)
LATCH_PIN = Pin(9, Pin.OUT)

SEG8Code = [0x5F, 0x42, 0x9B, 0xD3, 0xC6, 0xD5, 0xDD, 0x43, 0xDF, 0xD7, 0xCF, 0xDC, 0x1D, 0xDA, 0x9D, 0x8D]
BitsSelection = [0xFE, 0xFD, 0xFB, 0xF7]  # Digit selection (1st, 2nd, 3rd, 4th)

class LED_8SEG:
    def __init__(self):
        self.latch = LATCH_PIN
        self.clock = CLOCK_PIN
        self.data = DATA_PIN
        self.latch.value(1)
        self.clock.value(1)
        self.data.value(1)
        self.SEG8 = SEG8Code

    def Send_Bytes(self, dat):
        for _ in range(8):
            self.data.value(1 if dat & 0x80 else 0)
            dat = dat << 1
            self.clock.value(0)
            self.clock.value(1)

    def write_cmd(self, Num, Seg):
        self.Send_Bytes(Num)
        self.Send_Bytes(Seg)
        self.latch.value(0)
        self.latch.value(1)

# Initialize 7-segment display
display = LED_8SEG()

# --- System State Machine ---
class PressStateMachine:
    STATES = [
        'INIT', 'STARTUP_CHECK', 'MOTOR_WARMUP', 'IDLE',
        'WAIT_FOR_FILL', 'FAST_DOWN', 'SLOW_DOWN_HIGH_FORCE',
        'MOVE_UP', 'PRESS_FULL', 'MANUAL_UP', 'MANUAL_DOWN', 'ERROR'
    ]

    def __init__(self):
        self.state = 'INIT'
        self.last_state = None
        self.cycle_count = 0
        self.error_code = None
        self.timers = {
            'motor_warmup': 0,
            'fast_down': 0,
            'slow_down_transition': 0,
            'move_up_timeout': 0,
            'full_press_timer': 0,
            'cycle_timeout': 0
        }

    def set_state(self, new_state):
        if new_state in self.STATES:
            self.last_state = self.state
            self.state = new_state
            print(f"STATE: {self.state}")
            # Update 7-segment display
            self.update_display()
        else:
            print(f"ERROR: Invalid state {new_state}")

    def update_display(self):
        # Simple mapping for display
        state_map = {
            'INIT': 'INIT',
            'IDLE': ' IDL',
            'ERROR': 'ERR ',
            'FAST_DOWN': 'FDWN',
            'MOVE_UP': ' UP ',
            'PRESS_FULL': 'FULL'
        }
        text = state_map.get(self.state, '    ')
        # Convert text to display codes
        digits = []
        for char in text:
            if char == ' ':
                digits.append(0x00)  # Blank
            elif char.isdigit():
                digits.append(self.display.SEG8[int(char)])
            else:
                # Map letters (simplified)
                letter_map = {'I': 0x06, 'N': 0x76, 'T': 0x71, 'D': 0x5E, 'L': 0x38, 'E': 0x79, 'R': 0x5E, 'F': 0x71, 'U': 0x3F, 'P': 0x73}
                digits.append(letter_map.get(char, 0x00))

        # Update display (this is a simplified version)
        # In a real implementation, you'd create a task to refresh the display continuously
        for i in range(min(4, len(digits))):
            display.write_cmd(BitsSelection[i], digits[i] if i < len(digits) else 0x00)

    def get_state(self):
        return self.state

# Initialize state machine
state_machine = PressStateMachine()

# --- Helper Functions ---

def get_input_state(input_name):
    """Get the state of an input, respecting its pull configuration."""
    config = input_config[input_name]
    pin_value = config['pin'].value()
    if config['pull'] == 'up':
        return pin_value == 0  # Active LOW for pull-up
    else:  # pull-down
        return pin_value == 1  # Active HIGH for pull-down

def set_input_pull(input_name, pull_type):
    """Reconfigure an input pin with pull-up or pull-down."""
    if pull_type not in ['up', 'down']:
        return False
    pin_num = input_config[input_name]['pin'].id()  # Get the pin number
    # Reinitialize the pin
    if pull_type == 'up':
        input_config[input_name]['pin'] = Pin(pin_num, Pin.IN, Pin.PULL_UP)
    else:  # pull-down
        input_config[input_name]['pin'] = Pin(pin_num, Pin.IN, Pin.PULL_DOWN)
    input_config[input_name]['pull'] = pull_type
    return True

def stop_all_relays():
    """Emergency stop: turn off all relays."""
    RELAY_MOTOR.value(0)
    RELAY_DOOR.value(0)
    RELAY_12MB1.value(0)
    RELAY_12MB2.value(0)
    RELAY_13MB1.value(0)
    RELAY_13MB2.value(0)
    RELAY_RESERVE1.value(0)
    RELAY_RESERVE2.value(0)

def move_fast_down():
    """Activate fast downward movement."""
    RELAY_12MB1.value(1)
    RELAY_12MB2.value(0)
    RELAY_13MB1.value(0)
    RELAY_13MB2.value(0)

def move_slow_down_high_force():
    """Activate slow downward movement with high force."""
    RELAY_12MB1.value(1)
    RELAY_12MB2.value(0)
    RELAY_13MB1.value(1)
    RELAY_13MB2.value(0)

def move_up():
    """Activate upward movement."""
    RELAY_12MB1.value(0)
    RELAY_12MB2.value(1)
    RELAY_13MB1.value(0)
    RELAY_13MB2.value(1)

# --- Web Interface Handlers ---

@app.route('/')
async def index_handler(r, w):
    """Main control page."""
    try:
        # Read HTML content from external file
        with open('index.html', 'r') as f:
            html = f.read()
    except OSError:
        # Fallback error message if file can't be read
        html = """<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body><h1>Error: Unable to load index.html</h1></body>
</html>"""
    
    w.write(b'HTTP/1.0 200 OK\r\n')
    w.write(b'Content-Type: text/html; charset=utf-8\r\n')
    w.write(b'\r\n')
    w.write(html.encode())
    await w.drain()

@app.route('/api/status')
async def status_handler(r, w):
    """API endpoint to get current system status."""
    status_data = {
        'state': state_machine.get_state(),
        'cycle_count': state_machine.cycle_count,
        'outputs': {
            'motor': RELAY_MOTOR.value(),
            'door': RELAY_DOOR.value(),
            'relay_12mb1': RELAY_12MB1.value(),
            'relay_12mb2': RELAY_12MB2.value(),
            'relay_13mb1': RELAY_13MB1.value(),
            'relay_13mb2': RELAY_13MB2.value()
        },
        'inputs': {
            'start_btn': get_input_state('start_btn'),
            'manual_up_btn': get_input_state('manual_up_btn'),
            'manual_down_btn': get_input_state('manual_down_btn'),
            'emergency_stop_btn': get_input_state('emergency_stop_btn'),
            'press_top_sensor': get_input_state('press_top_sensor'),
            'press_bottom_sensor': get_input_state('press_bottom_sensor'),
            'door_open_sensor': get_input_state('door_open_sensor')
        },
        'input_config': {
            'start_btn': input_config['start_btn']['pull'],
            'manual_up_btn': input_config['manual_up_btn']['pull'],
            'manual_down_btn': input_config['manual_down_btn']['pull'],
            'emergency_stop_btn': input_config['emergency_stop_btn']['pull'],
            'press_top_sensor': input_config['press_top_sensor']['pull'],
            'press_bottom_sensor': input_config['press_bottom_sensor']['pull'],
            'door_open_sensor': input_config['door_open_sensor']['pull']
        }
    }
    
    import json
    json_str = json.dumps(status_data)
    
    w.write(b'HTTP/1.0 200 OK\r\n')
    w.write(b'Content-Type: application/json\r\n')
    w.write(b'\r\n')
    w.write(json_str.encode())
    await w.drain()

@app.route('/api/config', methods=['POST'])
async def config_handler(r, w):
    """API endpoint to update input configuration."""
    try:
        # Read the request body
        content_length = int(r.headers.get('content-length', 0))
        body = await r.read(content_length)
        import json
        config_data = json.loads(body.decode())
        
        # Update configurations
        success = True
        for input_name, pull_type in config_data.items():
            if input_name in input_config:
                if not set_input_pull(input_name, pull_type):
                    success = False
        
        if success:
            w.write(b'HTTP/1.0 200 OK\r\n')
            w.write(b'Content-Type: application/json\r\n')
            w.write(b'\r\n')
            w.write(b'{"status": "success"}')
        else:
            w.write(b'HTTP/1.0 400 Bad Request\r\n')
            w.write(b'Content-Type: application/json\r\n')
            w.write(b'\r\n')
            w.write(b'{"status": "error", "message": "Invalid configuration"}')
    except Exception as e:
        w.write(b'HTTP/1.0 500 Internal Server Error\r\n')
        w.write(b'Content-Type: application/json\r\n')
        w.write(b'\r\n')
        w.write(b'{"status": "error", "message": "Server error"}')
        print(f"Config handler error: {e}")
    
    await w.drain()

# --- Main System Task ---
async def system_task():
    """Main system control task implementing the finite state machine."""
    global state_machine
    
    while True:
        current_state = state_machine.get_state()
        
        try:
            if current_state == 'INIT':
                # Initialize hardware
                stop_all_relays()
                STATUS_LED.value(1)  # Turn on status LED
                state_machine.set_state('STARTUP_CHECK')
                
            elif current_state == 'STARTUP_CHECK':
                # Check all sensors
                door_open = get_input_state('door_open_sensor')
                emergency_stop = get_input_state('emergency_stop_btn')
                
                if door_open or emergency_stop:
                    # Stay in error state until conditions are resolved
                    state_machine.set_state('ERROR')
                else:
                    state_machine.set_state('IDLE')
                    
            elif current_state == 'IDLE':
                # Wait for start button
                if get_input_state('start_btn') and not get_input_state('emergency_stop_btn'):
                    RELAY_MOTOR.value(1)  # Start motor
                    state_machine.timers['motor_warmup'] = time.time() + 5  # 5 seconds warmup
                    state_machine.set_state('MOTOR_WARMUP')
                    
                # Check manual controls
                if get_input_state('manual_up_btn'):
                    state_machine.set_state('MANUAL_UP')
                elif get_input_state('manual_down_btn'):
                    state_machine.set_state('MANUAL_DOWN')
                    
            elif current_state == 'MOTOR_WARMUP':
                # Wait for motor warmup
                if time.time() >= state_machine.timers['motor_warmup']:
                    move_up()  # Move to top position
                    state_machine.timers['move_up_timeout'] = time.time() + 15  # 15 seconds timeout
                    state_machine.set_state('MOVE_UP')
                    
            elif current_state == 'MOVE_UP':
                # Wait for top position sensor
                if get_input_state('press_top_sensor'):
                    state_machine.set_state('WAIT_FOR_FILL')
                elif time.time() >= state_machine.timers['move_up_timeout']:
                    state_machine.error_code = "MOVE_UP_TIMEOUT"
                    state_machine.set_state('ERROR')
                    
            elif current_state == 'WAIT_FOR_FILL':
                # Wait for door to close and start cycle
                if not get_input_state('door_open_sensor') and get_input_state('start_btn'):
                    state_machine.timers['cycle_timeout'] = time.time() + 60  # 60 seconds for full cycle
                    move_fast_down()
                    state_machine.timers['fast_down'] = time.time() + 15  # 15 seconds fast down
                    state_machine.set_state('FAST_DOWN')
                    
            elif current_state == 'FAST_DOWN':
                # Fast downward movement
                if get_input_state('press_bottom_sensor'):
                    # Transition to slow down with high force
                    RELAY_12MB1.value(0)  # Turn off fast down
                    state_machine.timers['slow_down_transition'] = time.time() + 2  # Wait 2 seconds
                    state_machine.set_state('SLOW_DOWN_HIGH_FORCE')
                elif time.time() >= state_machine.timers['fast_down']:
                    # Timeout - transition to slow down anyway
                    RELAY_12MB1.value(0)
                    state_machine.timers['slow_down_transition'] = time.time() + 2
                    state_machine.set_state('SLOW_DOWN_HIGH_FORCE')
                    
            elif current_state == 'SLOW_DOWN_HIGH_FORCE':
                # Slow down with high force
                if time.time() >= state_machine.timers['slow_down_transition']:
                    # First, activate 13MB1 for 1 second
                    RELAY_13MB1.value(1)
                    state_machine.timers['slow_down_transition'] = time.time() + 1
                    # Then reactivate 12MB1
                    RELAY_12MB1.value(1)
                    
                # Check if we've reached bottom position for more than 10 seconds
                if get_input_state('press_bottom_sensor'):
                    if state_machine.timers['full_press_timer'] == 0:
                        state_machine.timers['full_press_timer'] = time.time()
                    elif time.time() - state_machine.timers['full_press_timer'] > 10:
                        state_machine.set_state('PRESS_FULL')
                else:
                    state_machine.timers['full_press_timer'] = 0  # Reset timer if not at bottom
                    
                # Check cycle timeout
                if time.time() >= state_machine.timers['cycle_timeout']:
                    state_machine.error_code = "CYCLE_TIMEOUT"
                    state_machine.set_state('ERROR')
                    
            elif current_state == 'PRESS_FULL':
                # Press is full - stop operations and open door
                stop_all_relays()
                RELAY_DOOR.value(1)  # Open door
                state_machine.cycle_count += 1
                state_machine.set_state('IDLE')  # Return to idle, allow manual up
                
            elif current_state == 'MANUAL_UP':
                # Manual upward movement
                if get_input_state('manual_up_btn') and not get_input_state('emergency_stop_btn'):
                    RELAY_MOTOR.value(1)
                    move_up()
                else:
                    stop_all_relays()
                    state_machine.set_state('IDLE')
                    
            elif current_state == 'MANUAL_DOWN':
                # Manual downward movement
                if get_input_state('manual_down_btn') and not get_input_state('emergency_stop_btn'):
                    RELAY_MOTOR.value(1)
                    move_fast_down()
                else:
                    stop_all_relays()
                    state_machine.set_state('IDLE')
                    
            elif current_state == 'ERROR':
                # Error state - stop everything
                stop_all_relays()
                STATUS_LED.value(0)  # Turn off status LED (or blink for error)
                
                # Wait for emergency stop to be released and door to be closed
                if not get_input_state('emergency_stop_btn') and not get_input_state('door_open_sensor'):
                    state_machine.error_code = None
                    state_machine.set_state('IDLE')
                    
            # Check emergency stop at all times
            if get_input_state('emergency_stop_btn'):
                stop_all_relays()
                state_machine.set_state('ERROR')
                
            # Check door open sensor during operations (except manual mode)
            if (current_state not in ['INIT', 'STARTUP_CHECK', 'IDLE', 'MANUAL_UP', 'MANUAL_DOWN', 'ERROR'] and 
                get_input_state('door_open_sensor')):
                stop_all_relays()
                state_machine.set_state('ERROR')
                
        except Exception as e:
            print(f"System task error: {e}")
            state_machine.error_code = "SYSTEM_ERROR"
            state_machine.set_state('ERROR')
        
        # Small delay to prevent blocking
        await asyncio.sleep(0.1)

# --- Display Update Task ---
async def display_task():
    """Task to continuously update the 7-segment display."""
    # This is a simplified version - in practice, you'd need to implement
    # proper multiplexing to avoid flickering
    while True:
        try:
            # Get current state for display
            state = state_machine.get_state()
            
            # Simple state to display mapping
            if state == 'ERROR':
                digits = [display.SEG8[0], display.SEG8[1], display.SEG8[1], display.SEG8[1]]  # "Err"
            elif state == 'IDLE':
                digits = [0x00, display.SEG8[0], display.SEG8[1], display.SEG8[2]]  # " 012" - placeholder
            elif state == 'FAST_DOWN':
                digits = [display.SEG8[0], display.SEG8[1], 0x00, 0x00]  # "01  " - placeholder
            else:
                # Default: show state as number or code
                state_num = state_machine.STATES.index(state) % 10000
                str_num = f"{state_num:04d}"
                digits = [display.SEG8[int(d)] for d in str_num]
            
            # Update each digit (very simplified - would flicker in real use)
            for i in range(4):
                display.write_cmd(BitsSelection[i], digits[i])
                await asyncio.sleep(0.001)  # Very short delay
                
        except Exception as e:
            print(f"Display task error: {e}")
            
        await asyncio.sleep(0.1)

# --- Main Execution ---
async def main():
    """Main function to initialize and run the system."""
    print("Starting Hydraulic Press Control System v1.1")
    
    # Create WiFi access point
    wifi = network.WLAN(network.AP_IF)
    wifi.active(True)
    wifi.config(essid=AP_SSID, password=AP_PASSWORD)
    
    # Wait for AP to activate
    while not wifi.active():
        await asyncio.sleep(0.1)
    
    print(f"WiFi AP started: {wifi.ifconfig()}")
    
    # Start web server
    asyncio.create_task(app.serve())
    print("Web server started")
    
    # Start system control task
    asyncio.create_task(system_task())
    print("System control task started")
    
    # Start display update task
    asyncio.create_task(display_task())
    print("Display task started")
    
    # Keep the main loop running
    while True:
        await asyncio.sleep(1)

# Run the system
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("System stopped by user")
    finally:
        asyncio.new_event_loop()  # Create a new event loop if needed