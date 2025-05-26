# barometer:indoor temp:indoor humidity:windspeed:windspeedavg:winddirection:windrose:temp30ft:temp5ft:humidity30ft:humidity5ft
import os, sys
def add_to_csv(string):
    parts = string.split(" time: ")
    weather_data = parts[0]
    rest = parts[1]

    time_str, ip, seq_no_label, seq_no_value = rest.strip().split()
    epoch_time = float(time_str)

    weather_fields = weather_data.split(":")
    row = weather_fields + [epoch_time, ip, seq_no_value]
    row = ",".join(map(str, row))
    row = f"{row}\n"

    csv_filename = "data/data.csv"

    # These are the headers that I know. I'm not sure what the other fields are for...
    # I also moved windrose behind winddirection
    headers = [
        "barometer", "indoor_temp", "indoor_humidity", "windspeed", "windspeedavg", 
        "windrose", "winddirection", "temp30ft", "temp5ft", "humidity30ft", "humidity5ft",
        "field12", "field13", "field14", "field15", "field16", "field17", "field18", "field19", "field20",
        "time", "ip", "seq_no"
    ]
    headers = ",".join(map(str, headers))
    headers += "\n"


    file_exists = os.path.isfile(csv_filename)
    if not file_exists:
        with open(csv_filename, mode='w') as csvfile:
            csvfile.write(headers)
    with open(csv_filename, mode='a') as csvfile:
        csvfile.write(row)

if __name__ == "__main__":
    args = sys.argv[1:]
    weather_input = " ".join(args)
    if (len(args) > 0) and " seq_no: " in str(weather_input):
        add_to_csv(str(weather_input))