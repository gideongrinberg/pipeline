# I generated the lightcurves for TIC 363963079 and TIC 404144841 using this program (lightcurves/)
# and our old pipeline (test_lightcurves/). This test program compares each folder to make sure that
# all of the requested lightcurves were generated. It also generates a PDF of the old and new lightcurves
# side by side we can make sure they're the same.
#
# I copied a bunch of code from the old pipeline so this is quite messy.

import os
import re
import pandas as pd
import lightkurve as lk
from astropy import units as u
import matplotlib.pyplot as plt

def mkdir(dir):
    try:
        os.mkdir(dir)
    except:
        pass

mkdir("./figures")

def listdir(dir):
    for file in os.listdir(dir):
        if not file.startswith("."):
            yield file

i = 0

def graph_lc(lc, ylim=None, epoch_time=None, period=None, title=None, ax=None):
    fig = None
    if period == None:
        period = lc.to_periodogram().period_at_max_power
    if epoch_time == None:
        epoch_time = lc.time[0]
        
    lc = lc.fold(period, epoch_time)
    lc = lc.remove_outliers(sigma=3)
    
    blc = lc.bin(u.Quantity(25, u.s))
    
    plt.style.use("seaborn-v0_8-notebook")

    if ax == None:
        fig, ax = plt.subplots()

    ax.scatter(lc["time"].value, lc["flux"], 4, "#1f77b4", alpha=0.1)
    ax.scatter(blc["time"].value, blc["flux"], 6, "#1f77b4", alpha=1)
    
    ax.set_title(title if title is not None else lc.meta["LABEL"])
    ax.set_xlabel("Phase")
    ax.set_ylabel("Flux")

    if ylim is not None:
        ax.set_ylim(-ylim, ylim)
    
    if fig != None:
        return fig

tex_document = """
\\documentclass{article}
\\usepackage{graphicx}
\\usepackage{caption}
\\begin{document}
"""

def add_figures(file1: str, file2: str, caption: str) -> str:
    # Template for the side-by-side figure layout
    figure_snippet = f"""
\\begin{{figure}}[h!]
    \\centering
    \\begin{{minipage}}{{0.45\\textwidth}}
        \\centering
        \\includegraphics[width=\\textwidth]{{{file1}}}
    \\end{{minipage}}%
    \\hfill
    \\begin{{minipage}}{{0.45\\textwidth}}
        \\centering
        \\includegraphics[width=\\textwidth]{{{file2}}}
    \\end{{minipage}}
    \\caption{{{caption}}}
\\end{{figure}}
"""

    # Append the snippet to the document output and return it
    return figure_snippet

for tic in listdir("./test_lightcurves"):
    assert os.path.isdir(f"./lightcurves/{tic}")
    for lc in listdir(f"./test_lightcurves/{tic}"):
        assert os.path.exists(f"./lightcurves/{tic}/{lc}")
        if lc.endswith(".csv"):
            old_csv = pd.read_csv(f"./test_lightcurves/{tic}/{lc}")
            new_csv = pd.read_csv(f"./lightcurves/{tic}/{lc}")

            old_lc = lk.LightCurve(time = old_csv.time, flux = old_csv.flux)
            old_lc.meta["LABEL"] = "Old Pipeline"

            new_lc = lk.LightCurve(time = new_csv.time, flux = new_csv.flux)
            new_lc.meta["LABEL"] = "New Pipeline"

            graph_lc(old_lc)
            plt.savefig(f"./figures/{i}_old.png")
            plt.close()

            graph_lc(new_lc)
            plt.savefig(f"./figures/{i}_new.png")
            plt.close()

            sector = re.findall(r"Sector([0-9]+).csv", lc)[0]
            tex_document += add_figures(f"./figures/{i}_old.png", f"./figures/{i}_new.png", f"TIC {tic} (Sector {sector})")

            i += 1

with open("validate.tex", "w") as f:
    f.write(tex_document + "\n\end{document}")
            




print("If no warnings have been generated, this test suite has run successfully.")