# Sensor Data Format Documentation

## Data File Format

The sensor data file (sensor_data.txt) contains weather station readings with the following format:

```
field1:field2:field3:...:field20 time: timestamp ip_address seq_no: sequence_number
```

## Field Definitions

The 20 colon-separated fields before "time:" are for **daviscupsout** sensor:

| Field # | Field Name        | Description                          | Unit/Format |
|---------|-------------------|--------------------------------------|-------------|
| 1       | rtBaroCurr        | Current barometric pressure          | inHg        |
| 2       | rtInsideTemp      | Inside temperature                   | °F          |
| 3       | rtInsideHum       | Inside humidity                      | %           |
| 4       | rtWindSpeed       | Instantaneous wind speed ← CFD       | mph         |
| 5       | rtWindAvgSpeed    | Average wind speed                   | mph         |
| 6       | rtWindDir         | Wind direction bearing ← CFD         | degrees     |
| 7       | rtWindDirRose     | Wind direction (compass)             | text        |
| 8       | rtXtraTemp1       | Extra temperature sensor 1           | °F          |
| 9       | rtXtraTemp2       | Extra temperature sensor 2           | °F          |
| 10      | rtXtraHum1        | Extra humidity sensor 1              | %           |
| 11      | rtXtraHum2        | Extra humidity sensor 2              | %           |
| 12      | rtRainRate        | Rain rate                            | in/hr       |
| 13      | rtUVLevel         | UV level                             | index       |
| 14      | rtSolarRad        | Solar radiation                      | W/m²        |
| 15      | rtDayRain         | Daily rain accumulation              | inches      |
| 16      | rtDayET           | Daily evapotranspiration             | inches      |
| 17      | rtMonthET         | Monthly evapotranspiration           | inches      |
| 18      | rtYearET          | Yearly evapotranspiration            | inches      |
| 19      | rtXmitBatt        | Transmitter battery status           | -           |
| 20      | rtBattVoltage     | Battery voltage                      | volts       |

## Example Data Line

```
29.67:69.8:42:2:3:315:NW:45:46:94:80:0.00:0.0:25:0.00:0.0000:0.000:0.000:0:4.6 time: 1765756669.4484450817 10.10.4.34 seq_no: 532857
```

Decoded:
- Barometric Pressure: 29.67 inHg
- Inside Temp: 69.8°F
- Inside Humidity: 42%
- **Wind Speed: 2 mph** (Field 4, index 3 - CRITICAL FOR CFD MODEL)
- Average Wind Speed: 3 mph
- **Wind Direction: 315°** (Field 6, index 5 - CRITICAL FOR CFD MODEL) 
- Wind Direction: NW
- Extra Temp 1: 45°F
- Extra Temp 2: 46°F
- Extra Hum 1: 94%
- Extra Hum 2: 80%
- Battery Voltage: 4.6V
- Timestamp: 1765756669.4484450817 (Unix epoch)

## Unit Conversions

### Wind Speed: mph to m/s
```
wind_speed_ms = wind_speed_mph * 0.44704
```

### Temperature: °F to °C
```
temp_celsius = (temp_fahrenheit - 32) * 5/9
```

### Pressure: inHg to Pa
```
pressure_pa = pressure_inhg * 3386.39
```

## Usage in Code

To extract wind data correctly from daviscupsout:
```python
line = "29.67:69.8:42:2:3:315:NW:45:..."
parts = line.split('time:')[0].strip().split(':')
wind_speed_mph = float(parts[3])  # Field 4, index 3
wind_dir_deg = float(parts[5])    # Field 6, index 5
wind_speed_ms = wind_speed_mph * 0.44704  # Convert to m/s
```

## Notes

- Current sensor: **daviscupsout** (woof://128.111.45.61/davisstations/daviscupsout)
- Wind speed is in Field 4 (index 3 in 0-based arrays)
- Wind direction bearing is in Field 6 (index 5 in 0-based arrays)
- Wind speed must be converted from mph to m/s for CFD simulations
- Timestamps are Unix epoch time (seconds since 1970-01-01 00:00:00 UTC)
- Reference: training/CJKREADME, training/data_processing/parse_daviscups.py
