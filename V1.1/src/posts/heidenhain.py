"""Heidenhain (TNC style) post - illustrative plain-text output."""
from posts.base import BasePost


class Post(BasePost):
    name = "Heidenhain (TNC style)"
    description = "Heidenhain-ish plain-text (L, CC, C) - illustrative post."

    variables = {"SAFE_Z": 10.0, "PARK_X": 0.0, "PARK_Y": 0.0}

    options = {
        "absolute": True, "metric": True, "use_i_j": False,
        "arc_clockwise": "CC", "arc_ccw": "C", "comment_paren": False,
        "leading_zero": False, "subroutines": False, "line_numbers": True,
        "use_wcs": False,
    }

    templates = {
        "program_start": "BEGIN PGM {name} MM\n",
        "wcs": "L X+0 Y+0 Z+0\n",
        "toolchange": "TOOL DEF {tool} L\n",
        "spin_on": "M03 SPIN{rpm:.0f}\n",
        "cool_on": "M07\n",
        "cool_off": "M09\n",
        "rapid": "L X{x:.3f} Y{y:.3f} Z{z:.3f} R0 FMAX\n",
        "plunge": "L Z{z:.3f} F{f:.0f}\n",
        "cut_linear": "L X{x:.3f} Y{y:.3f} F{f:.0f}\n",
        "cut_arc_cw": "CC X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n",
        "cut_arc_ccw": "C X{x:.3f} Y{y:.3f} I{i:.3f} J{j:.3f} F{f:.3f}\n",
        "comp_on": "SL {code} D{dnum}\n",
        "comp_off": "SL OFF\n",
        "dwell": "PAUSE SEC{p:.2f}\n",
        "spin_off": "M05\n",
        "rapid_home": "L Z{z:.3f} FMAX\nL X{x:.3f} Y{y:.3f} FMAX\n",
        "program_end": "END PGM {name} MM\n",
        "comment": "; {text}\n",
    }
