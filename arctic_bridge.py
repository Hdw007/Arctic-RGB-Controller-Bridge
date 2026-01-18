import socket
import serial
import serial.tools.list_ports
import time
import sys
import ctypes
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Config ---
# Double check VID/PID values in device manager if your Arctic RGB controller is not recognized
WLED_UDP_PORT = 21324
WLED_HTTP_PORT = 80
TARGET_VID = 0x1A86
TARGET_PID = 0x7523
HEADER = bytes([0x01, 0x02, 0x03, 0xFF, 0x05, 0xFF, 0x02, 0x03])

# --- I/O Mapping ---
# Should not need to be changed, useful for debug or other software. Options are RGB / GBR
INPUT_MAPPING = "RGB"
OUTPUT_MAPPING = "RGB" 

# --- Spoofed WLED data (taken from an ESP32) ---
FAKE_INFO = {
    "ver": "0.15.3", "vid": 2508020, "cn": "ArcticBridge", "release": "ESP32", "repo": "wled/WLED",
    "deviceId": "dd6af53b90e913e31b393da78e3a56e9b19f510f65",
    "leds": { "count": 4, "pwr": 100, "fps": 60, "maxpwr": 9000, "maxseg": 1, "seglc": [1,1,1,1,1], "lc": 1, "rgbw": False, "wv": 0, "cct": 0 },
    "name": "Arctic Bridge", "udpport": 21324, "live": True,
    "wifi": { "bssid": "72:42:7F:4F:46:4D", "rssi": -50, "signal": 100, "channel": 9, "ap": False },
    "arch": "esp32", "core": "v3.3.6", "brand": "WLED", "product": "FOSS", "mac": "76ee4d009999", "ip": "127.0.0.1"
}
FAKE_STATE = {"on": True, "bri": 255, "udpn": {"send": False, "recv": True}}
FULL_RESPONSE = {"state": FAKE_STATE, "info": FAKE_INFO}

# Global Vars
DEBUG_MODE = False
ser = None

def process_colors(raw_r, raw_g, raw_b):
    # 1. INPUT
    if INPUT_MAPPING == "RGB":
        r, g, b = raw_r, raw_g, raw_b
    elif INPUT_MAPPING == "BGR":
        r, g, b = raw_b, raw_g, raw_r
    else:
        r, g, b = raw_r, raw_g, raw_b

    # 2. OUTPUT
    if OUTPUT_MAPPING == "GRB":
        return g, r, b
    elif OUTPUT_MAPPING == "BGR":
        return b, g, r
    else:
        return r, g, b # RGB Standard

# --- HTTP Server for WLED ---
class WLEDRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*') 
        self.end_headers()
    def do_GET(self):
        path = self.path.rstrip('/')
        self._set_headers()
        if path.endswith('/json/info'):
            self.wfile.write(json.dumps(FAKE_INFO).encode('utf-8'))
        elif path.endswith('/json/state'):
            self.wfile.write(json.dumps(FAKE_STATE).encode('utf-8'))
        elif path.endswith('/json'):
            self.wfile.write(json.dumps(FULL_RESPONSE).encode('utf-8'))
        else:
            self.wfile.write(json.dumps(FAKE_INFO).encode('utf-8'))

def start_http_server():
    try:
        HTTPServer(('0.0.0.0', WLED_HTTP_PORT), WLEDRequestHandler).serve_forever()
    except Exception as e:
        log(f"HTTP Server Error: {e}")

# --- Debug mode ---
def setup_console():
    global DEBUG_MODE
    if "-console" in sys.argv or "--console" in sys.argv:
        DEBUG_MODE = True
        if sys.platform == "win32":
            try:
                ctypes.windll.kernel32.AllocConsole()
                sys.stdout = open("CONOUT$", "w")
                sys.stderr = open("CONOUT$", "w")
            except: pass
        print("=== ARCTIC RGB BRIDGE ===")

def log(msg):
    if DEBUG_MODE:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
        sys.stdout.flush()

def connect_serial():
    ports = serial.tools.list_ports.comports()
    dev = None
    for port in ports:
        if port.vid == TARGET_VID and port.pid == TARGET_PID:
            dev = port.device; break
    if not dev: return None
    try:
        s = serial.Serial(dev, 250000, stopbits=serial.STOPBITS_TWO, timeout=0.1)
        s.write(HEADER + bytes([92, 1, 254, 1, 254]))
        log(f"Serial connected: {dev}")
        return s
    except: return None

# --- Main ---
def main():
    global ser
    setup_console()
    
    ser = connect_serial()
    while not ser:
        log("Searching for controller...")
        time.sleep(3)
        ser = connect_serial()

    threading.Thread(target=start_http_server, daemon=True).start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", WLED_UDP_PORT))
    except Exception as e:
        log(f"UDP Bind Error: {e}")
        return
    
    current_input_colors = [0] * 12 

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            valid = False
            
            # --- Parsing ---
            # WARLS (1)
            if len(data) > 2 and data[0] == 1: 
                i = 2
                while i < len(data) - 3:
                    if data[i] < 4:
                        base = data[i] * 3
                        current_input_colors[base:base+3] = data[i+1:i+4]
                    i += 4
                valid = True
            
            # DRGB (2) - Offset 2
            elif len(data) > 2 and data[0] == 2: 
                count = min(len(data)-2, 12)
                current_input_colors[:count] = data[2:2+count]
                valid = True
                
            # DNRGB (4) - Offset 4
            elif len(data) > 4 and data[0] == 4: 
                count = min(len(data)-4, 12)
                current_input_colors[:count] = data[4:4+count]
                valid = True
                
            # DDP (64)
            elif len(data) > 10 and (data[0] & 0xC0) == 0x40: 
                 count = min(len(data)-10, 12)
                 current_input_colors[:count] = data[10:10+count]
                 valid = True

            # --- Handle data ---
            if ser and valid:
                payload = bytearray([0x00])
                
                r_in = current_input_colors[0]
                g_in = current_input_colors[1]
                b_in = current_input_colors[2]

                # Smart Mirror Logic
                if r_in == 0 and g_in == 0 and b_in == 0:
                     for k in range(3, 12, 3):
                         if current_input_colors[k] > 0 or current_input_colors[k+1] > 0 or current_input_colors[k+2] > 0:
                             r_in, g_in, b_in = current_input_colors[k], current_input_colors[k+1], current_input_colors[k+2]
                             break

                # Mapping
                f1, f2, f3 = process_colors(r_in, g_in, b_in)
                
                v1 = 254 if f1 == 255 else f1
                v2 = 254 if f2 == 255 else f2
                v3 = 254 if f3 == 255 else f3

                for _ in range(4):
                    payload.append(v1); payload.append(v2); payload.append(v3)

                ser.write(HEADER + payload)

        except KeyboardInterrupt:
            break
        except Exception:
            try: ser.close()
            except: pass
            ser = connect_serial()

if __name__ == "__main__":
    main()