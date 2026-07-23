"""Siemens 840D post (different arc words / WCS style)."""
from posts.base import BasePost


class Post(BasePost):
    name = "Siemens 840D"
    description = "Siemens ISO turn/mill style (G54 WCS, different arc words)."

    variables = {"SAFE_Z": 10.0, "PARK_X": 0.0, "PARK_Y": 0.0}

    options = {
        "absolute": True, "metric": True, "use_i_j": False,
        "arc_clockwise": "G02", "arc_ccw": "G03",
        "comment_paren": True, "leading_zero": False,
        "subroutines": False, "line_numbers": False, "use_wcs": True,
    }

    templates = {
        "program_start": "%\n(--- {name} ---)\nG71 G90 G17\n",
        "wcs": "G54\n",
        "toolchange": "T{tool} D{tool}\n",
        "spin_on": "M03 S{rpm:.0f}\n",
        "cool_on": "M07\n",
        "cool_off": "M09\n",
        "rapid": "G00 X{x:.3f} Y{y:.3f} Z{z:.3f}\n",
        "plunge": "G01 Z{z:.3f} F{f:.0f}\n",
        "cut_linear": "G01 X{x:.3f} Y{y:.3f} F{f:.0f}\n",
        "cut_arc_cw": "G02 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n",
        "cut_arc_ccw": "G03 X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n",
        "comp_on": "{code} D{dnum}\n",
        "comp_off": "G40\n",
        "dwell": "G04 F{p:.2f}\n",
        "spin_off": "M05\n",
        "rapid_home": "G00 Z{z:.3f}\nG00 X{x:.3f} Y{y:.3f}\n",
        "program_end": "M30\n%\n",
        "comment": "({text})\n",
    }
