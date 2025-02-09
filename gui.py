import pandas as pd
import dearpygui.dearpygui as dpg

from pipeline import load_lc
from astropy import units as u
import matplotlib.colors as mcolors

##############
# App Setup #
############

dpg.create_context()
dpg.configure_app(
    init_file="custom_layout.ini", load_init_file=True, docking=True, docking_space=True
)
dpg.create_viewport(title="Custom Title", width=600, height=300)

#####################
# Global Variables #
####################

settings = dpg.generate_uuid()
tic_list = dpg.generate_uuid()
sector_list = dpg.generate_uuid()
graph_viewer = dpg.generate_uuid()

state = {
    "dir": None,
    "df": None,
    "table": [],
    "selected_tic": None,
    "selected_sector": None,
}

####################################
# Callbacks and Utility Functions #
###################################

def hex_to_rgba(hex_color, alpha=1.0):
    """Convert hex color (e.g. "#d3d3d3") to an RGBA list with values 0-255."""
    rgb = mcolors.to_rgb(hex_color)  # returns tuple of floats between 0 and 1
    return [int(255 * x) for x in rgb] + [int(255 * alpha)]

def graph_lc(sector):
    lc = load_lc(state["selected_tic"], sector)
    flc = lc.remove_outliers().fold(period=lc.to_periodogram().period_at_max_power)
    blc = flc.bin(u.Quantity(40, u.s))

    # Convert data to lists
    x1 = list(flc["time"].value)
    y1 = list(flc["flux"])
    x2 = list(blc["time"].value)
    y2 = list(blc["flux"])

    with dpg.theme(tag="theme_series1"):
         with dpg.theme_component(dpg.mvScatterSeries):
             # Marker size ~14 and light gray (#d3d3d3) at 70% opacity.
            #  dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerSize, 14, category=dpg.mvThemeCat_Plots)
             dpg.add_theme_color(dpg.mvPlotCol_Line, hex_to_rgba("#d3d3d3", 0.7), category=dpg.mvThemeCat_Plots)
    
    with dpg.theme(tag="theme_series2"):
         with dpg.theme_component(dpg.mvScatterSeries):
             # Marker size ~20 and blue (#1f77b4) at full opacity.
            #  dpg.add_theme_style(dpg.mvPlotStyleVar_MarkerSize, 20, category=dpg.mvThemeCat_Plots)
             dpg.add_theme_color(dpg.mvPlotCol_Line, hex_to_rgba("#1f77b4", 1.0), category=dpg.mvThemeCat_Plots)
    
    # Add a plot to the given parent container.
    with dpg.plot(label="Light Curve", parent=graph_viewer, width=-1, height=-1):
         dpg.add_plot_legend()

         # Create the x and y axes. Here we tag the y-axis so the series know which axis to attach to.
         dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="x_axis")
         dpg.add_plot_axis(dpg.mvYAxis, label="Flux", tag="y_axis")
         
         # Add the two scatter series as children of the y-axis.
         dpg.add_scatter_series(x1, y1, label="Folded LC", parent="y_axis", tag="series1")
         dpg.add_scatter_series(x2, y2, label="Binned LC", parent="y_axis", tag="series2")
         
         # Bind the themes to the series.
         dpg.bind_item_theme("series1", "theme_series1")
         dpg.bind_item_theme("series2", "theme_series2")

def sector_callback(sector):
    def callback():
        graph_lc(sector)

    return callback


def tic_callback(tic):
    def callback():
        state["selected_tic"] = tic

        df = state["df"]
        df = df[df["TIC"] == tic].sort_values(by="Sector")

        if dpg.does_item_exist("sector_table"):
            rows = dpg.get_item_children("sector_table", slot=1)
            for row in rows:
                dpg.delete_item(row)

        for _, row in df.iterrows():
            row = row.to_dict()
            with dpg.table_row(parent="sector_table"):
                dpg.add_button(
                    label=f"Sector {row['Sector']}",
                    callback=sector_callback(row["Sector"]),
                )
                dpg.add_text("Y" if row["Complex"] else "")

    return callback


def save_clicked():
    state["dir"] = dpg.get_value("folder")
    state["df"] = pd.read_csv(dpg.get_value("csv"))

    state["table"] = (
        state["df"]
        .groupby(["TIC", "Complex"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .to_numpy()
        .tolist()
    )

    # Clear existing rows before adding new ones
    if dpg.does_item_exist("tics_table"):
        rows = dpg.get_item_children("tics_table", slot=1)
        for row in rows:
            dpg.delete_item(row)

    for row in state["table"]:
        with dpg.table_row(parent="tics_table"):
            dpg.add_button(label=str(row[0]), callback=tic_callback(row[0]))
            dpg.add_text(str(row[1]))
            dpg.add_text(str(row[2]))
##############
# App Logic #
#############

with dpg.window(label="Settings", id=settings):
    dpg.add_text("Settings")
    with dpg.group(horizontal=True):
        dpg.add_text("Lightcurves Folder:")
        dpg.add_input_text(tag="folder", default_value="./lightcurves")
    with dpg.group(horizontal=True):
        dpg.add_text("Pipeline Output:")
        dpg.add_input_text(tag="csv", default_value="output.csv")
    dpg.add_button(label="Save", callback=save_clicked)

with dpg.window(label="TIC List", id=tic_list):
    with dpg.table(tag="tics_table", header_row=True):
        dpg.add_table_column(label="TIC", tag="col_tic")
        dpg.add_table_column(label="# Complex", tag="col_num_complex")
        dpg.add_table_column(label="# Not Complex", tag="col_num_notcomplex")

with dpg.window(label="Sector List", id=sector_list):
    with dpg.table(tag="sector_table", header_row=True):
        dpg.add_table_column(label="Sector", tag="col_sector")
        dpg.add_table_column(label="Complex?", tag="col_sector_complex")

with dpg.window(label="Graph Viewer", id=graph_viewer):
    pass

dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
