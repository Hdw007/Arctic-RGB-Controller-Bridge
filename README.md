# Arctic Bridge

A Python script that bridges WLED UDP protocols (WARLS, DRGB, DNRGB, DDP) to the Arctic RGB controller via Serial. This allows you to control your Arctic RGB fans/strips using WLED software (like SignalRGB, xLights, or the WLED app).

## Requirements

*   Python 3.x
*   Arctic RGB Controller (VID: `0x1A86`, PID: `0x7523`)

## Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the script:
```bash
python arctic_bridge.py
```

To enable the debug console window (Windows only):
```bash
python arctic_bridge.py --console
```