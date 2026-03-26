#!/usr/bin/env python3
"""
Explore sensor historical data to determine wind speed/direction range for CFD simulations.

Note: At this pipeline stage, we're processing SENSOR HISTORICAL DATA (not ML training data yet).
This data will be used to configure and run CFD simulations. The ML model training happens
later using CFD simulation results.

Current sensor: daviscupsout (woof://128.111.45.61/davisstations/daviscupsout)

CSPOT sensor data format for daviscupsout (colon-delimited, 20 fields before "time:"):
  Field 1 (index 0): rtBaroCurr (barometric pressure, inHg)
  Field 2 (index 1): rtInsideTemp (inside temperature, °F)
  Field 3 (index 2): rtInsideHum (inside humidity, %)
  Field 4 (index 3): rtWindSpeed (instantaneous wind speed, mph) ← USED FOR CFD
  Field 5 (index 4): rtWindAvgSpeed (average wind speed, mph)
  Field 6 (index 5): rtWindDir (wind direction bearing, degrees 0-359) ← USED FOR CFD
  Field 7 (index 6): rtWindDirRose (wind direction compass, text: N/NE/E/...)
  Field 8 (index 7): rtXtraTemp1 (extra temperature sensor 1, °F)
  Field 9 (index 8): rtXtraTemp2 (extra temperature sensor 2, °F)
  Field 10 (index 9): rtXtraHum1 (extra humidity sensor 1, %)
  Field 11 (index 10): rtXtraHum2 (extra humidity sensor 2, %)
  Fields 12-20: Rain, UV, Solar, Battery, etc.

Reference: training/CJKREADME, training/data_processing/parse_daviscups.py
  dcout.csv uses --indexes 3,5 for windspeed,direction
"""

import sys
import csv
from datetime import datetime
from pathlib import Path
from collections import defaultdict

def log_info(msg):
    print(f"[INFO] {datetime.now().strftime('%H:%M:%S')} {msg}")

def log_error(msg):
    print(f"[ERROR] {datetime.now().strftime('%H:%M:%S')} {msg}", file=sys.stderr)

# Conversion factor: 1 mph = 0.44704 m/s
MPH_TO_MS = 0.44704

def parse_csv_file(filepath):
    """
    Parse wind data from CSV file with columns: dt,windspeed,windavg,winddir
    
    This is the new format created by the data exploration notebook.
    NOTE: Wind speed in sensor data is in mph, converted to m/s here.
    Example:
        dt,windspeed,windavg,winddir
        2024-11-11 09:41:01.546797,0.0,0.0,299.0
        2024-11-11 09:46:05.826348,1.0,0.0,201.0
    
    Returns list of dicts with 'speed' (m/s) and 'direction' keys.
    """
    results = []
    parse_errors = 0
    
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                wind_speed_mph = float(row['windspeed'])
                wind_dir = float(row['winddir'])
                
                # Skip invalid values (-1 is sentinel for bad data)
                if wind_speed_mph < 0 or wind_dir < 0:
                    parse_errors += 1
                    continue
                
                # Validate wind direction is in valid range (0-359)
                if not (0 <= wind_dir <= 360):
                    parse_errors += 1
                    continue
                
                # Validate wind speed is reasonable (0-112 mph ~ 0-50 m/s)
                if not (0 <= wind_speed_mph <= 112):
                    parse_errors += 1
                    continue
                
                # Convert mph to m/s
                wind_speed_ms = wind_speed_mph * MPH_TO_MS
                
                results.append({"speed": wind_speed_ms, "direction": wind_dir})
            except (ValueError, KeyError) as e:
                parse_errors += 1
                continue
    
    return results, parse_errors


def parse_wind_data_from_line(line):
    """
    Parse wind data from CSPOT data line (legacy format).
    
    Current sensor: daviscupsout (confirmed by main.sh WOOF URL)
    Field 4 (index 3) = rtWindSpeed (instantaneous wind speed in mph)
    Field 6 (index 5) = rtWindDir (numeric bearing in degrees, 0-359)
    
    Reference: training/CJKREADME and training/data_processing/parse_daviscups.py
    dcout uses --indexes 3,5 for windspeed,direction
    
    Sample daviscupsout line:
    29.67:69.8:42:2:3:315:NW:45:46:94:80:0.00:0.0:25:0.00:0.0000:0.000:0.000:0:4.6 time: ...
                    ^  ^^^
                    |3||5|
                 Speed Dir(deg)
    """
    try:
        # Find " time:" to separate data from metadata
        time_marker = " time:"
        if time_marker not in line:
            return None
        
        # Get everything before " time:"
        data_part = line.split(time_marker)[0].strip()
        fields = data_part.split(':')
        
        # We need at least up to field 6 for wind direction
        if len(fields) < 6:
            return None
        
        try:
            # Field 4 (index 3) = rtWindSpeed (instantaneous wind speed in mph)
            # Field 6 (index 5) = rtWindDir (numeric bearing in degrees, 0-359)
            
            wind_speed_mph = float(fields[3])
            wind_dir = float(fields[5])
            
            # Validate wind direction is in valid range (0-359)
            if not (0 <= wind_dir <= 359):
                return None
            
            # Validate wind speed is reasonable (0-112 mph ~ 0-50 m/s)
            if not (0 <= wind_speed_mph <= 112):
                return None
            
            # Convert mph to m/s
            wind_speed_ms = wind_speed_mph * MPH_TO_MS
            
            return {"speed": wind_speed_ms, "direction": wind_dir}
        except (ValueError, IndexError):
            return None
        
    except (ValueError, IndexError):
        return None

def explore_training_data(training_file, mode='stats'):
    """
    Explore the sensor historical data file to determine wind speed/direction range and statistics.
    This data will be used to configure CFD simulations (not ML model training at this stage).
    
    Args:
        training_file: Path to training_data.txt file (sensor historical data)
        mode: 'stats' (default) for statistical analysis, 'unique_pairs' to output unique
              windspeed-direction pairs, or 'unique_integer' to output unique integer wind speeds
    
    Returns:
        Dict with wind data statistics, unique pairs list, or unique integer speeds
    """
    training_path = Path(training_file)
    
    if not training_path.exists():
        log_error(f"Training file not found: {training_file}")
        return None
    
    log_info(f"Exploring training data: {training_file}")
    log_info(f"Mode: {mode}")
    
    # Read all lines and parse wind data
    wind_speeds = []
    wind_directions = []
    wind_pairs = set()  # For unique pairs
    record_count = 0
    parse_errors = 0
    
    # Check if this is a CSV file with header
    is_csv = str(training_path).endswith('.csv')
    with open(training_path, 'r') as f:
        first_line = f.readline().strip()
        # Check for CSV header with our expected columns
        if 'windspeed' in first_line.lower() and 'winddir' in first_line.lower():
            is_csv = True
    
    if is_csv:
        # Use new CSV parser
        results, parse_errors = parse_csv_file(training_path)
        record_count = len(results) + parse_errors
        for wind_data in results:
            wind_speeds.append(wind_data['speed'])
            wind_directions.append(wind_data['direction'])
            pair = (round(wind_data['speed'], 2), int(wind_data['direction']))
            wind_pairs.add(pair)
    else:
        # Use legacy CSPOT parser
        with open(training_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                record_count += 1
                wind_data = parse_wind_data_from_line(line)
                
                if wind_data:
                    wind_speeds.append(wind_data['speed'])
                    wind_directions.append(wind_data['direction'])
                    # Store unique pairs (rounded to 2 decimal places for speed, integer for direction)
                    pair = (round(wind_data['speed'], 2), int(wind_data['direction']))
                    wind_pairs.add(pair)
                else:
                    parse_errors += 1
    
    if not wind_speeds:
        log_error("No valid wind data found in training data")
        return None
    
    if mode == 'unique_integer':
        # Extract unique integer wind speed values
        unique_integer_speeds = set(int(round(speed)) for speed in wind_speeds)
        
        # Calculate median wind direction for use with all unique integer speeds
        wind_directions_sorted = sorted(wind_directions)
        n = len(wind_directions_sorted)
        if n % 2 == 0:
            median_dir = int((wind_directions_sorted[n // 2 - 1] + wind_directions_sorted[n // 2]) / 2)
        else:
            median_dir = int(wind_directions_sorted[n // 2])
        
        return {
            "file": str(training_path),
            "total_records": record_count,
            "valid_records": len(wind_speeds),
            "parse_errors": parse_errors,
            "unique_integer_speeds": unique_integer_speeds,
            "median_direction": median_dir,
        }
    
    if mode == 'unique_pairs':
        return {
            "file": str(training_path),
            "total_records": record_count,
            "valid_records": len(wind_speeds),
            "parse_errors": parse_errors,
            "unique_pairs": wind_pairs,
        }
    
    # Default 'stats' mode
    # Calculate statistics
    wind_speeds.sort()
    wind_directions.sort()
    
    min_speed = wind_speeds[0]
    max_speed = wind_speeds[-1]
    avg_speed = sum(wind_speeds) / len(wind_speeds)
    
    # Calculate median wind direction
    n = len(wind_directions)
    if n % 2 == 0:
        median_dir = (wind_directions[n//2 - 1] + wind_directions[n//2]) / 2
    else:
        median_dir = wind_directions[n//2]
    
    stats = {
        "file": str(training_path),
        "total_records": record_count,
        "valid_records": len(wind_speeds),
        "parse_errors": parse_errors,
        "wind_speed_min": min_speed,
        "wind_speed_max": max_speed,
        "wind_speed_avg": avg_speed,
        "wind_dir_median": median_dir,
    }
    
    return stats

def main():
    if len(sys.argv) < 2:
        log_error("Usage: explore_training_data.py <sensor_data_file> [mode]")
        log_error("  mode: 'stats' (default), 'unique_pairs', or 'unique_integer'")
        sys.exit(1)
    
    sensor_file = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else 'stats'
    
    if mode not in ['stats', 'unique_pairs', 'unique_integer']:
        log_error(f"Invalid mode '{mode}'. Must be 'stats', 'unique_pairs', or 'unique_integer'")
        sys.exit(1)
    
    result = explore_training_data(sensor_file, mode=mode)
    
    if not result:
        sys.exit(1)
    
    if mode == 'unique_integer':
        # Output unique integer wind speeds and create CSV file
        unique_speeds = result['unique_integer_speeds']
        median_dir = result['median_direction']
        speeds_list = sorted(list(unique_speeds))
        
        print("\n=== Unique Integer Wind Speed Values ===")
        print(f"File: {result['file']}")
        print(f"Total records: {result['total_records']}")
        print(f"Valid records: {result['valid_records']}")
        if result['parse_errors'] > 0:
            print(f"Parse errors: {result['parse_errors']}")
        print(f"Unique integer speeds: {len(speeds_list)}")
        print(f"Speeds: {speeds_list}")
        print(f"Median wind direction: {median_dir}°")
        
        # Create CSV file with speed and mean direction
        csv_filename = Path(result['file']).stem + "_unique_integer.csv"
        try:
            with open(csv_filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['wind_speed_m_s'])
                for speed in speeds_list:
                    writer.writerow([speed])
            log_info(f"CSV file created: {csv_filename}")
            print(f"\nCSV output: {csv_filename}")
            print(f"Total unique integer speeds written: {len(speeds_list)}")
        except IOError as e:
            log_error(f"Failed to write CSV file: {e}")
            sys.exit(1)
        
        # Print environment-friendly format
        print(f"\nUNIQUE_INTEGER_COUNT={len(speeds_list)}")
        print(f"UNIQUE_INTEGER_CSV={csv_filename}")
        print(f"WIND_DIR_MEDIAN={median_dir}")
    
    elif mode == 'unique_pairs':
        # Output unique pairs and create CSV file
        unique_pairs = result['unique_pairs']
        pairs_list = sorted(list(unique_pairs))
        
        print("\n=== Unique Wind Speed - Wind Direction Pairs ===")
        print(f"File: {result['file']}")
        print(f"Total records: {result['total_records']}")
        print(f"Valid records: {result['valid_records']}")
        if result['parse_errors'] > 0:
            print(f"Parse errors: {result['parse_errors']}")
        print(f"Unique pairs: {len(pairs_list)}")
        
        # Create CSV file
        csv_filename = Path(result['file']).stem + "_unique_pairs.csv"
        try:
            with open(csv_filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['wind_speed_m_s', 'wind_direction_degrees'])
                for speed, direction in pairs_list:
                    writer.writerow([speed, direction])
            log_info(f"CSV file created: {csv_filename}")
            print(f"\nCSV output: {csv_filename}")
            print(f"Total unique pairs written: {len(pairs_list)}")
        except IOError as e:
            log_error(f"Failed to write CSV file: {e}")
            sys.exit(1)
        
        # Print environment-friendly format
        print(f"\nUNIQUE_PAIRS_COUNT={len(pairs_list)}")
        print(f"UNIQUE_PAIRS_CSV={csv_filename}")
    
    else:  # 'stats' mode
        # Print summary
        stats = result
        print("\n=== Training Data Exploration (Stats Mode) ===")
        print(f"File: {stats['file']}")
        print(f"Total records: {stats['total_records']}")
        print(f"Valid records: {stats['valid_records']}")
        if stats['parse_errors'] > 0:
            print(f"Parse errors: {stats['parse_errors']}")
        
        print(f"\n=== Wind Speed Range ===")
        print(f"Min speed: {stats['wind_speed_min']:.2f} m/s")
        print(f"Max speed: {stats['wind_speed_max']:.2f} m/s")
        print(f"Avg speed: {stats['wind_speed_avg']:.2f} m/s")
        
        print(f"\n=== Wind Direction ===")
        print(f"Median direction: {stats['wind_dir_median']:.1f}°")
        
        # Output as environment-friendly format
        print(f"\nWIND_SPEED_MIN={stats['wind_speed_min']:.2f}")
        print(f"WIND_SPEED_MAX={stats['wind_speed_max']:.2f}")
        print(f"WIND_SPEED_AVG={stats['wind_speed_avg']:.2f}")
        print(f"WIND_DIR_MEDIAN={stats['wind_dir_median']:.0f}")
        print(f"VALID_RECORDS={stats['valid_records']}")

if __name__ == "__main__":
    main()
