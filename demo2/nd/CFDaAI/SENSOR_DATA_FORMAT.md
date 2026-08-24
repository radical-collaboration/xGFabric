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

---

## wu-30 / wu-31 / wu-32 Indoor Weather Stations

Three indoor Davis weather stations (wu-30, wu-31, wu-32) that transmit over LoRa OTA.
Each station has two woof feeds with the same colon-delimited format:

| Woof suffix    | Message type | Content                                  |
|----------------|--------------|------------------------------------------|
| `*-ota-data`   | 56           | temperature, humidity, **wind speed**    |
| `*-ota-storm`  | 49           | **wind speed**, wind direction, rain     |

Both message types report the **same wind speed** (average over the 36-second transmission window). Wind is sampled every 4 seconds; the average of those samples is sent.

### Woof URLs

| Station | ota-data woof                                              | ota-storm woof                                               | CFD position    |
|---------|------------------------------------------------------------|--------------------------------------------------------------|-----------------|
| wu-30   | `woof://128.111.45.61/davisstations/wu-30-ota-data`        | `woof://128.111.45.61/davisstations/wu-30-ota-storm`         | x=166, y=48, z=1 |
| wu-31   | `woof://128.111.45.61/davisstations/wu-31-ota-data`        | `woof://128.111.45.61/davisstations/wu-31-ota-storm`         | x=104, y=48, z=1 |
| wu-32   | `woof://128.111.45.61/davisstations/wu-32-ota-data`        | `woof://128.111.45.61/davisstations/wu-32-ota-storm`         | TBD             |

### Field Layout (0-based, colon-delimited)

| Index | Field name        | Unit   | Notes                                         |
|-------|-------------------|--------|-----------------------------------------------|
| 0     | epoch_time        | s      | Unix timestamp (integer part)                 |
| 1     | utc_time          | —      | `YYYY-MM-DD_HH_MM_SS`                         |
| 2     | id                | —      | Station ID                                    |
| 3     | channel           | —      | e.g. `A`                                      |
| 4     | message_type      | —      | 56 = ota-data, 49 = ota-storm                 |
| 5     | battery_status    | —      |                                               |
| 6     | rssi_db           | dBm    |                                               |
| 7     | snr_db            | dB     |                                               |
| 8     | frequency_mhz     | MHz    |                                               |
| **9** | **wind_speed_km_h** | **km/h** | **← USE THIS — average over 36 s window** |
| 10    | wind_dir_deg      | °      | ota-storm only; `-1` in ota-data              |
| 11    | rain_in           | in     | ota-storm only; `-1` in ota-data              |
| 12    | temperature_F     | °F     | ota-data only; `-999` in ota-storm            |
| 13    | humidity          | %      | ota-data only                                 |
| 14    | dew_point_F       | °F     |                                               |
| 15    | heat_index_F      | °F     |                                               |
| 16    | wind_chill        | °F     | `-999` = no wind chill (calm or hot)          |

### Invalid / missing values

- `-1` — field not reported for this message type
- `-999` — value not applicable (e.g. wind_chill when calm)
- **Always skip any wind speed < 0**

### Example records

```
# ota-data (message_type=56)
1780431763:2026-06-02_13_22_43:1978:A:56:1:-0.127:24.857:433.949:2.656:-1:-1:103.1:24:59.3:103.8:-999 time: 1780431763.9946539402 192.168.101.58 seq_no: 26449

# ota-storm (message_type=49)
1780431781:2026-06-02_13_23_01:1978:A:49:1:-0.104:25.413:433.948:0.0:292.5:1.06:-999:-1:59.3:103.8:-999 time: 1780431782.3445351124 192.168.101.58 seq_no: 26474
```

### Unit conversion

```python
KMH2MS = 1 / 3.6
wind_speed_ms = float(fields[9]) * KMH2MS   # skip if value < 0
```

### Fetch rate

Packets are sent every **36 seconds** ≈ 2400 records/day per woof.
Size the `n_recs` buffer accordingly (vs 288/day for daviscups).

```python
lookback_h = (datetime.now(tz=UTC) - t_start).total_seconds() / 3600
n_recs = int(lookback_h / 24 * 2400 * 1.5) + 200
```

### Wind direction note (ota-storm / message_type 49)

When `wind_speed == 0` there is **no valid wind direction** in message type 49.
Always check speed before using direction.

### Known issue: wu-31 excluded from active evaluation (2026-07-08)

Checked a 24h live window of `wu-31-ota-data`: 2360/2360 records, but 2357 of
them (100%, in two runs of 831 and 1523 consecutive points) read exactly
0.0 -- not intermittent dropouts, effectively no real wind signal being
reported at all for that whole stretch. wu-30 over the same window was much
healthier (74% zero, but mostly short 1-3 point runs consistent with normal
low-wind dithering, not a dead sensor).

Because of this, `wu31` is commented out of `INDOOR_SENSOR_SPECS` in
`steps/verify_period/compute_mae.py` and out of `SENSOR_SPECS`/
`INDOOR_SENSORS` in `steps/verify_period/fetch_sensors.py` -- it no longer
participates in MAE evaluation or gets fetched by the verify_period scripts.
Re-enable it there once wu-31 is confirmed reporting real data again (a
short healthy run, not just nonzero -- a stuck-nonzero sensor would be just
as unusable).

See also `steps/verify_period/clean_indoor_sensor_data.py` ("Real Data
Processing") for how *brief* zero dropouts (wu-30/davis_in's 1-3 point
runs, likely cup-anemometer stall/dithering near the rounding threshold,
not equipment failure) are distinguished from genuine calm/outage and
repaired before evaluation -- that's a separate, narrower problem from
wu-31's wholesale lack of signal handled here.

### Real Data Processing applied to davis_in / wu30 (2026-07-08)

As of 2026-07-08, `davis_in` and `wu30` readings are run through
`clean_indoor_sensor_data.py::clean_zero_dropouts()` before use in
`compute_v_shape_curve.py` and the `plot_3type_sensor_predictions.py` /
`plot_3model_sensor_predictions.py` diagnostics: zero-value runs up to 3
points long are replaced with a straight-line (time-weighted) interpolation
between that run's own immediate flanking readings, on the assumption
they're brief dropouts inside a real, otherwise-active wind reading, not
genuine calm. Longer runs are left untouched. This is now treated as the
true reading going forward for anything downstream (norm_mae curves,
similarity comparisons, etc.).

This has NOT been independently validated against known-good ground truth
(e.g. a period with an unambiguous external wind record) -- it's a
reasonable-looking heuristic backed only by the run-length histogram
(21 short davis_in runs / 109 short wu30 runs vs. much longer 6+/100+ point
runs, see above), not a proven-correct correction. The 3-point run-length
cutoff and the choice of linear interpolation (vs. e.g. holding the last
value) are both judgment calls. Revisit/re-examine this if downstream
results look sensitive to it, or if a genuinely trustworthy reference
reading ever becomes available to check against.
