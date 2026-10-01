# Create variables
Yaw = 0
Throttle = 0
Roll = 0
Pitch = 0

# Import dependencies
import serial
from flask import Flask, jsonify, request
import os
import socket
import threading
from datetime import datetime

# The RPi hosts a WiFi hotspot named "hotspot" (see setup_hotspot.sh), so the
# control PC never needs a static IP - it just joins the WiFi and uses this.
HOTSPOT_IP = os.environ.get('HOTSPOT_IP', '192.168.4.1')

# Init pyserial
serial = serial.Serial('/dev/ttyUSB0')
serial.baudrate = 115200
serial.write(b'0;0;0;0')


# Motor config, Only Normal for now
# 1 is Normal
Motorconf = 1

# Flask web app
app = Flask(__name__)
gamepad_data = {
    'left_stick_x': 0.0,
    'left_stick_y': 0.0,
    'right_stick_x': 0.0,
    'right_stick_y': 0.0,
    'left_trigger': 0.0,
    'right_trigger': 0.0,
    'dpad_x': 0,
    'dpad_y': 0,
    'button_a': False,
    'button_b': False,
    'button_x': False,
    'button_y': False,
    'lb': False,
    'rb': False,
    'back': False,
    'start': False,
    'left_stick_click': False,
    'right_stick_click': False,
    'timestamp': None
}

data_lock = threading.Lock()

HTML_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ROVcoPILOT Surface Control Panel</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            color: #fff;
            padding: 20px;
        }
        
        .container {
            background: rgba(0, 0, 0, 0.7);
            border-radius: 15px;
            padding: 30px;
            max-width: 900px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            border: 2px solid #00ff88;
        }
        
        h1 {
            text-align: center;
            margin-bottom: 10px;
            color: #00ff88;
            font-size: 2.5em;
            text-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
        }
        
        .status {
            text-align: center;
            margin-bottom: 25px;
            font-size: 0.9em;
            color: #aaa;
        }
        
        .status.connected {
            color: #00ff88;
        }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 25px;
        }
        
        .section {
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid #00ff88;
            border-radius: 10px;
            padding: 20px;
        }
        
        .section h2 {
            color: #00ff88;
            margin-bottom: 15px;
            font-size: 1.2em;
            border-bottom: 1px solid #00ff88;
            padding-bottom: 10px;
        }
        
        .stick-container {
            margin-bottom: 20px;
        }
        
        .stick-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 0.9em;
        }
        
        .stick-visual {
            width: 100%;
            height: 150px;
            background: radial-gradient(circle at center, #1a1a1a 0%, #0a0a0a 100%);
            border: 2px solid #00ff88;
            border-radius: 10px;
            position: relative;
            margin-bottom: 10px;
        }
        
        .stick-dot {
            width: 20px;
            height: 20px;
            background: #00ff88;
            border-radius: 50%;
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            box-shadow: 0 0 10px #00ff88;
        }
        
        .center-cross {
            position: absolute;
            width: 100%;
            height: 100%;
            top: 0;
            left: 0;
        }
        
        .center-cross::before,
        .center-cross::after {
            content: '';
            position: absolute;
            background: rgba(0, 255, 136, 0.2);
        }
        
        .center-cross::before {
            width: 1px;
            height: 100%;
            left: 50%;
            top: 0;
        }
        
        .center-cross::after {
            height: 1px;
            width: 100%;
            top: 50%;
            left: 0;
        }
        
        .value-display {
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            background: #1a1a1a;
            padding: 8px;
            border-radius: 5px;
            color: #00ff88;
        }
        
        .trigger-container {
            margin-bottom: 20px;
        }
        
        .trigger-bar {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .trigger-label {
            width: 80px;
            font-size: 0.9em;
        }
        
        .trigger-visual {
            flex: 1;
            height: 30px;
            background: #1a1a1a;
            border: 1px solid #00ff88;
            border-radius: 5px;
            overflow: hidden;
            position: relative;
        }
        
        .trigger-fill {
            height: 100%;
            background: linear-gradient(90deg, #00ff88, #00cc6f);
            width: 0%;
            transition: width 0.05s;
            box-shadow: 0 0 10px rgba(0, 255, 136, 0.5);
        }
        
        .trigger-value {
            width: 50px;
            text-align: right;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            color: #00ff88;
        }
        
        .buttons-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 10px;
        }
        
        .button {
            padding: 15px;
            border: 2px solid #00ff88;
            background: #1a1a1a;
            color: #00ff88;
            border-radius: 8px;
            font-weight: bold;
            text-align: center;
            cursor: pointer;
            transition: all 0.1s;
            font-size: 0.9em;
        }
        
        .button.pressed {
            background: #00ff88;
            color: #000;
            box-shadow: 0 0 20px #00ff88;
            transform: scale(0.95);
        }
        
        .dpad {
            display: grid;
            grid-template-columns: repeat(3, 40px);
            gap: 5px;
            justify-content: center;
            margin: 15px 0;
        }
        
        .dpad-btn {
            width: 40px;
            height: 40px;
            border: 1px solid #00ff88;
            background: #1a1a1a;
            color: #00ff88;
            border-radius: 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            cursor: default;
            transition: all 0.1s;
        }
        
        .dpad-btn.pressed {
            background: #00ff88;
            color: #000;
            box-shadow: 0 0 10px #00ff88;
        }
        
        .full-width {
            grid-column: 1 / -1;
        }
        
        .timestamp {
            text-align: center;
            color: #888;
            font-size: 0.85em;
            margin-top: 20px;
            border-top: 1px solid #00ff88;
            padding-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ROVcoPILOT</h1>
        <div class="status" id="status">Waiting for gamepad...</div>
        
        <div class="grid">
            <!-- Left Column -->
            <div>
                <div class="section">
                    <h2>Left Stick</h2>
                    <div class="stick-container">
                        <div class="stick-label">
                            <span>X: <span id="lsx">0.00</span></span>
                            <span>Y: <span id="lsy">0.00</span></span>
                        </div>
                        <div class="stick-visual">
                            <div class="center-cross"></div>
                            <div class="stick-dot" id="leftStickDot"></div>
                        </div>
                        <div class="value-display">
                            X: <span id="lsx-val">0.00</span> | Y: <span id="lsy-val">0.00</span>
                        </div>
                    </div>
                </div>
                
                <div class="section" style="margin-top: 20px;">
                    <h2>D-Pad</h2>
                    <div style="text-align: center;">
                        <div class="dpad">
                            <div class="dpad-btn"></div>
                            <div class="dpad-btn" id="dpadUp">↑</div>
                            <div class="dpad-btn"></div>
                            <div class="dpad-btn" id="dpadLeft">←</div>
                            <div class="dpad-btn" style="background: #333; border: none;"></div>
                            <div class="dpad-btn" id="dpadRight">→</div>
                            <div class="dpad-btn"></div>
                            <div class="dpad-btn" id="dpadDown">↓</div>
                            <div class="dpad-btn"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Right Column -->
            <div>
                <div class="section">
                    <h2>Right Stick</h2>
                    <div class="stick-container">
                        <div class="stick-label">
                            <span>X: <span id="rsx">0.00</span></span>
                            <span>Y: <span id="rsy">0.00</span></span>
                        </div>
                        <div class="stick-visual">
                            <div class="center-cross"></div>
                            <div class="stick-dot" id="rightStickDot"></div>
                        </div>
                        <div class="value-display">
                            X: <span id="rsx-val">0.00</span> | Y: <span id="rsy-val">0.00</span>
                        </div>
                    </div>
                </div>
                
                <div class="section" style="margin-top: 20px;">
                    <h2>Triggers</h2>
                    <div class="trigger-container">
                        <div class="trigger-bar">
                            <span class="trigger-label">LT:</span>
                            <div class="trigger-visual">
                                <div class="trigger-fill" id="ltFill"></div>
                            </div>
                            <span class="trigger-value" id="ltVal">0.00</span>
                        </div>
                    </div>
                    <div class="trigger-container">
                        <div class="trigger-bar">
                            <span class="trigger-label">RT:</span>
                            <div class="trigger-visual">
                                <div class="trigger-fill" id="rtFill"></div>
                            </div>
                            <span class="trigger-value" id="rtVal">0.00</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Buttons Section -->
        <div class="section">
            <h2>Buttons</h2>
            <div class="buttons-grid">
                <button class="button" id="btnA">A</button>
                <button class="button" id="btnB">B</button>
                <button class="button" id="btnX">X</button>
                <button class="button" id="btnY">Y</button>
                <button class="button" id="btnLB">LB</button>
                <button class="button" id="btnRB">RB</button>
                <button class="button" id="btnBack">Back</button>
                <button class="button" id="btnStart">Start</button>
                <button class="button full-width" id="btnLStick">Left Stick</button>
                <button class="button full-width" id="btnRStick">Right Stick</button>
            </div>
        </div>
        
        <div class="timestamp">
            Last update: <span id="timestamp">Never</span>
        </div>
    </div>
    
    <script>
        // Gamepad API reading
        let gamepadIndex = -1;
        const updateInterval = 50; // milliseconds
        
        // Scale stick value to visual position (0-150px within 75px radius)
        function stickToPixels(value) {
            return 75 + (value * 75);
        }
        
        function updateDisplay() {
            const gamepads = navigator.getGamepads();
            
            if (gamepadIndex === -1) {
                for (let i = 0; i < gamepads.length; i++) {
                    if (gamepads[i]) {
                        gamepadIndex = i;
                        document.getElementById('status').textContent = 
                            `✓ Gamepad Connected: ${gamepads[i].id}`;
                        document.getElementById('status').classList.add('connected');
                        break;
                    }
                }
            }
            
            if (gamepadIndex === -1) return;
            
            const gamepad = gamepads[gamepadIndex];
            
            if (!gamepad) {
                gamepadIndex = -1;
                document.getElementById('status').textContent = 'Gamepad Disconnected';
                document.getElementById('status').classList.remove('connected');
                return;
            }
            
            // Read all axes and buttons
            const data = {
                leftStickX: gamepad.axes[0] || 0,
                leftStickY: gamepad.axes[1] || 0,
                rightStickX: gamepad.axes[2] || 0,
                rightStickY: gamepad.axes[3] || 0,
                leftTrigger: (gamepad.axes[4] || -1 + 1) / 2, // Normalize to 0-1
                rightTrigger: (gamepad.axes[5] || -1 + 1) / 2,
                buttonA: gamepad.buttons[0]?.pressed || false,
                buttonB: gamepad.buttons[1]?.pressed || false,
                buttonX: gamepad.buttons[2]?.pressed || false,
                buttonY: gamepad.buttons[3]?.pressed || false,
                LB: gamepad.buttons[4]?.pressed || false,
                RB: gamepad.buttons[5]?.pressed || false,
                back: gamepad.buttons[8]?.pressed || false,
                start: gamepad.buttons[9]?.pressed || false,
                leftStickClick: gamepad.buttons[10]?.pressed || false,
                rightStickClick: gamepad.buttons[11]?.pressed || false,
                dpadX: ((gamepad.buttons[15]?.pressed ? 1 : 0) - (gamepad.buttons[14]?.pressed ? 1 : 0)),
                dpadY: ((gamepad.buttons[12]?.pressed ? 1 : 0) - (gamepad.buttons[13]?.pressed ? 1 : 0))
            };
            
            // Update left stick
            document.getElementById('lsx').textContent = data.leftStickX.toFixed(2);
            document.getElementById('lsy').textContent = data.leftStickY.toFixed(2);
            document.getElementById('lsx-val').textContent = data.leftStickX.toFixed(2);
            document.getElementById('lsy-val').textContent = data.leftStickY.toFixed(2);
            document.getElementById('leftStickDot').style.transform = 
                `translate(calc(-50% + ${data.leftStickX * 75}px), calc(-50% + ${data.leftStickY * 75}px))`;
            
            // Update right stick
            document.getElementById('rsx').textContent = data.rightStickX.toFixed(2);
            document.getElementById('rsy').textContent = data.rightStickY.toFixed(2);
            document.getElementById('rsx-val').textContent = data.rightStickX.toFixed(2);
            document.getElementById('rsy-val').textContent = data.rightStickY.toFixed(2);
            document.getElementById('rightStickDot').style.transform = 
                `translate(calc(-50% + ${data.rightStickX * 75}px), calc(-50% + ${data.rightStickY * 75}px))`;
            
            // Update triggers
            document.getElementById('ltVal').textContent = data.leftTrigger.toFixed(2);
            document.getElementById('ltFill').style.width = (data.leftTrigger * 100) + '%';
            document.getElementById('rtVal').textContent = data.rightTrigger.toFixed(2);
            document.getElementById('rtFill').style.width = (data.rightTrigger * 100) + '%';
            
            // Update buttons
            updateButton('btnA', data.buttonA);
            updateButton('btnB', data.buttonB);
            updateButton('btnX', data.buttonX);
            updateButton('btnY', data.buttonY);
            updateButton('btnLB', data.LB);
            updateButton('btnRB', data.RB);
            updateButton('btnBack', data.back);
            updateButton('btnStart', data.start);
            updateButton('btnLStick', data.leftStickClick);
            updateButton('btnRStick', data.rightStickClick);
            
            // Update D-pad
            document.getElementById('dpadUp').classList.toggle('pressed', data.dpadY > 0);
            document.getElementById('dpadDown').classList.toggle('pressed', data.dpadY < 0);
            document.getElementById('dpadLeft').classList.toggle('pressed', data.dpadX < 0);
            document.getElementById('dpadRight').classList.toggle('pressed', data.dpadX > 0);
            
            // Send to server
            fetch('/api/gamepad', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(r => {
                if (r.ok) {
                    const now = new Date();
                    document.getElementById('timestamp').textContent = 
                        now.toLocaleTimeString('en-US', {hour12: false});
                }
            });
        }
        
        function updateButton(id, pressed) {
            const btn = document.getElementById(id);
            btn.classList.toggle('pressed', pressed);
        }
        
        setInterval(updateDisplay, updateInterval);
        updateDisplay();
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Serve the embedded webpage"""
    return HTML_PAGE


@app.route('/api/gamepad', methods=['GET'])
def get_gamepad_data():
    """Return current gamepad data as JSON"""
    with data_lock:
        data = gamepad_data.copy()
    return jsonify(data)


@app.route('/api/gamepad', methods=['POST'])
def update_gamepad_data():
    """Update gamepad data from client"""
    global gamepad_data
    
    try:
        new_data = request.get_json()
        
        with data_lock:
            gamepad_data['left_stick_x'] = float(new_data.get('leftStickX', 0.0))
            gamepad_data['left_stick_y'] = float(new_data.get('leftStickY', 0.0))
            gamepad_data['right_stick_x'] = float(new_data.get('rightStickX', 0.0))
            gamepad_data['right_stick_y'] = float(new_data.get('rightStickY', 0.0))
            gamepad_data['left_trigger'] = float(new_data.get('leftTrigger', 0.0))
            gamepad_data['right_trigger'] = float(new_data.get('rightTrigger', 0.0))
            gamepad_data['dpad_x'] = int(new_data.get('dpadX', 0))
            gamepad_data['dpad_y'] = int(new_data.get('dpadY', 0))
            gamepad_data['button_a'] = bool(new_data.get('buttonA', False))
            gamepad_data['button_b'] = bool(new_data.get('buttonB', False))
            gamepad_data['button_x'] = bool(new_data.get('buttonX', False))
            gamepad_data['button_y'] = bool(new_data.get('buttonY', False))
            gamepad_data['lb'] = bool(new_data.get('LB', False))
            gamepad_data['rb'] = bool(new_data.get('RB', False))
            gamepad_data['back'] = bool(new_data.get('back', False))
            gamepad_data['start'] = bool(new_data.get('start', False))
            gamepad_data['left_stick_click'] = bool(new_data.get('leftStickClick', False))
            gamepad_data['right_stick_click'] = bool(new_data.get('rightStickClick', False))
            gamepad_data['timestamp'] = datetime.now().isoformat()
        
        return jsonify({'status': 'success'}), 200
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@app.route('/api/status', methods=['GET'])
def get_status():
    """Return server status"""
    with data_lock:
        timestamp = gamepad_data['timestamp']
    
    return jsonify({
        'status': 'running',
        'last_update': timestamp,
        'gamepad_connected': timestamp is not None
    })

# Sending data to console, For early tests
# def print_gamepad_data():
#     """Periodically print gamepad data to console"""
#     import time
#     while True:
#         time.sleep(1)
#         with data_lock:
#             if gamepad_data['timestamp'] is not None:
#                 print("\n" + "="*60)
#                 print(f"Gamepad Data ({gamepad_data['timestamp']})")
#                 print("="*60)
#                 print(f"Left Stick:  X={gamepad_data['left_stick_x']:6.2f}, Y={gamepad_data['left_stick_y']:6.2f}")
#                 print(f"Right Stick: X={gamepad_data['right_stick_x']:6.2f}, Y={gamepad_data['right_stick_y']:6.2f}")
#                 print(f"Triggers:    LT={gamepad_data['left_trigger']:6.2f}, RT={gamepad_data['right_trigger']:6.2f}")
#                 print(f"D-Pad:       X={gamepad_data['dpad_x']:2d}, Y={gamepad_data['dpad_y']:2d}")
#                 print(f"Buttons:     A={gamepad_data['button_a']}, B={gamepad_data['button_b']}, " +
#                       f"X={gamepad_data['button_x']}, Y={gamepad_data['button_y']}")
#                 print(f"Bumpers:     LB={gamepad_data['lb']}, RB={gamepad_data['rb']}")
#                 print(f"Menu:        BACK={gamepad_data['back']}, START={gamepad_data['start']}")
#                 print(f"Stick Click: L={gamepad_data['left_stick_click']}, R={gamepad_data['right_stick_click']}")
#                 print("="*60)


import time

Yaw, Throttle, Roll, Pitch = 0.0, 0.0, 0.0, 0.0
M1, M2, M3, M4 = 0.0, 0.0, 0.0, 0.0

def save_joy():
    global Yaw, Throttle, Roll, Pitch
    Yaw = gamepad_data.get('left_stick_x', 0.0)  
    Throttle = gamepad_data.get('left_stick_y', 0.0)   
    Roll = gamepad_data.get('right_stick_x', 0.0)
    Pitch = gamepad_data.get('right_stick_y', 0.0)

def calc_motor():
    global M1, M2, M3, M4
    if Motorconf == 1:
        M1 = Throttle - Yaw
        M2 = Throttle + Yaw
        M3 = Pitch - Roll
        M4 = Pitch + Roll   
        
        M1 = max(-1.0, min(1.0, M1))
        M2 = max(-1.0, min(1.0, M2))
        M3 = max(-1.0, min(1.0, M3))
        M4 = max(-1.0, min(1.0, M4))

def send_data():
    cmd = f"{M1:.2f};{M2:.2f};{M3:.2f};{M4:.2f}\n"
    if serial and serial.is_open:
        serial.write(cmd.encode('utf-8'))

def rov_control_thread():
    while True:
        save_joy()
        calc_motor()
        send_data()
        time.sleep(0.1)











def local_addresses():
    """Every address this machine answers on, so we can print the right URL."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            found.add(info[4][0])
    except (socket.gaierror, OSError):
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((HOTSPOT_IP, 9))
        found.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return found


def print_banner(port):
    addresses = local_addresses()
    # Plain ASCII on purpose: a plain "ssh pi@192.168.4.1" session often has no
    # UTF-8 locale, and box-drawing characters would crash the print.
    print("+--------------------------------------------------+")
    print("|          ROVcoPILOT Server Starting...           |")
    print("+--------------------------------------------------+")
    print(f"\n  Hotspot IP : {HOTSPOT_IP}")
    for address in sorted(addresses):
        print(f"  Also at   : http://{address}:{port}")
    if HOTSPOT_IP not in addresses:
        print(f"\n  !! {HOTSPOT_IP} is not an address on this machine.")
        print("  !! The WiFi hotspot is not running. Start it once with:")
        print("  !!     sudo ./setup_hotspot.sh")
    print()


# When WebServer Starts
if __name__ == '__main__':
    thread1 = threading.Thread(target=rov_control_thread, daemon=True)
    thread1.start()

    port = int(os.environ.get('PORT', 80))
    print_banner(port)

    # Run Flask app - no debugger, it would expose a console on the network
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
