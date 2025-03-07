import os
import sys
import math
from argparse import ArgumentParser


import zipfile


def update_by_val(vx, vy, vz, core_folder_path):
    if not os.path.exists(core_folder_path):
        raise Exception(f"Provided path '{core_folder_path}' does not exist")
    if not os.path.exists(os.path.join(core_folder_path, "0", "U")):
        raise Exception(f"Provided path '{core_folder_path}' does not contain U file")
    with open(os.path.join(core_folder_path, "0", "U"), "rt") as f:
        text = f.read()
    inlet_loc = text.find("inlet")
    if inlet_loc == -1:
        raise Exception("No inlet found")
    uniform_loc = text.find("uniform", inlet_loc)
    if uniform_loc == -1:
        raise Exception("No uniform found")
    start = text.find("(", uniform_loc)
    end = text.find(")", uniform_loc)
    if start == -1 or end == -1:
        raise Exception("No brackets found")
    start += 1
    text = text[:start] + f"{vx} {vy} {vz}" + text[end:]
    with open(os.path.join(core_folder_path, "0", "U"), "wt") as f:
        f.write(text)

def speed_and_dir_2_xyz(windspeed, winddir):
    if winddir == "N":
        angle=0
    elif winddir == "NNE":
        angle=0.44
    elif winddir == "NE":
        angle=0.79
    elif winddir == "E":
        angle=1.57
    elif winddir == "SE":
        angle=2.36
    elif winddir == "SSE":
        angle=2.7
    elif winddir == "S":
        angle=3.14
    elif winddir == "SSW":
        angle=3.58
    elif winddir == "SW":
        angle=3.93
    elif winddir == "W":
        angle=4.71
    elif winddir == "NW":
        angle=5.5
    elif winddir == "NNW":
        angle=5.85
    else:
        angle=0 # Just for now, will fix later
    return windspeed * math.cos(angle), windspeed * math.sin(angle), 0


if __name__ == "__main__":
    parser = ArgumentParser()
    # parser.add_argument("vx", type=float, help="X component of velocity")
    # parser.add_argument("vy", type=float, help="Y component of velocity")
    # parser.add_argument("vz", type=float, help="Z component of velocity")

    parser.add_argument("windspeed", type=float, help="Windspeed average value")
    parser.add_argument("winddir", type=str, help="Wind direction [N, S, W, E, SW, etc]")
    parser.add_argument("-f", "--file", dest="filename",
                        help="filename for core files list", default="small_structure.zip")

    args = parser.parse_args()
    windspeed = int(args.windspeed)
    x, y, z = speed_and_dir_2_xyz(windspeed, args.winddir)
    foldername = "testfstrucutre"
    with zipfile.ZipFile(args.filename, 'r') as zip_ref:
        zip_ref.extractall(foldername)


    
    update_by_val(x, y, z, os.path.join(foldername,"small_structure"))
