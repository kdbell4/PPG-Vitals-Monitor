# PPG Vitals Monitor

A finger-clip vitals monitor built from scratch. Monitors standard vitals (heart rate, blood oxygen).

- Created with kicad schematic, which prototyped on a breadboard
  
  - PCB design is on the roadmap

- Firmware samples the output of the sensor, and a live plot tool reads those serial samples and generates a graph to analyze the waveform

- Finger Jig, a CAD model for holding the LED and photodiode in alignment across a finger

## Repo layout

| Path              | Contents                                                   |
| ----------------- | ---------------------------------------------------------- |
| `ppg_platformio/` | Teensy 4.0 firmware (PlatformIO + Arduino framework)       |
| `ppg_circuit/`    | KiCad project — schematic and PCB for the analog front end |
| `CAD/`            | FreeCAD parts                                              |

## Hardware Used

- **Photodiode**: BPW34
- **Op-amp**: MCP6002
- **MCU**: Teensy 4.0

## Signal Path for Sensor

```
Red + IR LEDs (660nm / 940nm)
        |
        v
   Finger (tissue) -- absorbs pulsing blood
        |
        v
Photodiode + TIA -- converts light to voltage
        |
        v
Passive filter + gain -- isolates the pulse signal
        |
        v
MCU: ADC + firmware -- heart rate, SpO2, bio-ID match
        |
        v
     Display -- vitals + identity
```

## CAD

3D-printed parts (`CAD/`) hold the LED and photodiode in stable optical
alignment across the fingertip. Built in FreeCAD; STLs are exported for slicing and
printing.
