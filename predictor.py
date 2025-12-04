#!/usr/bin/env python3
from __future__ import annotations

"""
This is the python file that will be used to predict the
posstion of the satellites based on the user location.

Optional Ideas to Expand Later
Plot satellite path on a map (with matplotlib or basemap)
GUI with Tkinter
Voice command to pick satellite (e.g., ISS)
Show live ground track on Earth
"""


"""
Functions of the predictor.py file
------------------------------------
Read the TLE data from the selected tle file.
To do the above, you must make use of open.

"""

"""
predictor.py
------------
This module is the "math brain" of your tracker. It takes:
  - Two TLE lines (line1, line2) that describe a satellite's orbit
  - An observer location on Earth (latitude, longitude, optional altitude)
and predicts:
  - When the satellite rises above your horizon (rise time)
  - When it reaches maximum elevation (culmination)
  - When it sets below your horizon (set time)
  - Plus instantaneous Azimuth/Elevation at each step if you want to display it

It uses:
  - sgp4: to propagate the satellite state (position/velocity) in ECI/TEME
  - Basic coordinate transforms:
      * ECI (inertial) -> ECEF (Earth-fixed, rotates with Earth)
      * ECEF satellite - ECEF observer -> topocentric ENU (East, North, Up)
      * ENU -> Azimuth/Elevation

You can read this file top-to-bottom and understand what's going on.
"""

import math
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# sgp4 gives us satellite propagation from TLEs
from sgp4.api import Satrec, jday

# ----------------------------
# Constants (WGS84 Earth model)
WGS84_A = 6378137.0  # This is the radius of the earth around the equator (The Semi Majot Axis)

# Flattening
WGS84_F = 1.0 / 298.257223563
#This is the flattening factor.
#It tells us how much the Earth is squashed compared to a perfect sphere.

# First eccentricity squared
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
# Speed-of-Earth rotation is handled via GMST angle; we don't need omega_E here.


# ---------------------------------
# Data structures for clean returns
# ---------------------------------
@dataclass
class PassEvent:
    """One satellite visibility pass window for the observer."""
    rise_time_utc: datetime
    max_time_utc: datetime
    max_elevation_deg: float
    set_time_utc: datetime
    rise_azimuth_deg: float
    set_azimuth_deg: float


@dataclass
class SamplePoint:
    """One time-sampled point of the pass solution (for plotting or live display)."""
    time_utc: datetime
    azimuth_deg: float
    elevation_deg: float
    range_km: float


# -------------------------------------------------------
# Utility: degrees/radians helpers (keep code readable)
# -------------------------------------------------------
def d2r(deg: float) -> float: #degrees to radian
    return deg * math.pi / 180.0


def r2d(rad: float) -> float: #radians to degrees
    return rad * 180.0 / math.pi



# Step 1: Greenwich Mean Sidereal Time (GMST) / θ_g

def gmst_angle(dt_utc: datetime) -> float:
    """
    Compute the GMST angle (radians) for a given UTC datetime.
    This rotates ECI -> ECEF around Earth's Z axis.

    Formula: (Vallado/IAU-82 approximation — plenty accurate for pass prediction)
      GMST (deg) = 280.46061837
                   + 360.98564736629 * (JD - 2451545.0)
                   + 0.000387933 * T^2
                   - (T^3)/38710000
      where T = (JD - 2451545.0)/36525  (Julian centuries since J2000)

    We then wrap to [0, 360) and convert to radians.
    """
    # Julian Day / fraction from sgp4 helper
    jd, fr = jday(dt_utc.year, dt_utc.month, dt_utc.day,
                  dt_utc.hour, dt_utc.minute, dt_utc.second + dt_utc.microsecond * 1e-6)
    jd_ut1 = jd + fr  # treat UT1≈UTC for our purposes
    T = (jd_ut1 - 2451545.0) / 36525.0

    gmst_deg = (280.46061837
                + 360.98564736629 * (jd_ut1 - 2451545.0)
                + 0.000387933 * (T ** 2)
                - (T ** 3) / 38710000.0)
    gmst_deg = gmst_deg % 360.0
    return d2r(gmst_deg)



# Step 2: Observer geodetic -> ECEF (Earth-fixed XYZ)

def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float = 0.0) -> Tuple[float, float, float]:
    """
    Convert geodetic (lat, lon in degrees, altitude meters) -> ECEF XYZ in meters.

    WGS84 ellipsoid formulas:
      N(phi) = a / sqrt(1 - e^2 sin^2(phi))
      x = (N + h) cos phi cos lambda
      y = (N + h) cos phi sin lambda
      z = (N (1 - e^2) + h) sin phi
    """
    lat = d2r(lat_deg)
    lon = d2r(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    N = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)

    x = (N + alt_m) * cos_lat * cos_lon
    y = (N + alt_m) * cos_lat * sin_lon
    z = (N * (1.0 - WGS84_E2) + alt_m) * sin_lat
    return x, y, z



# Step 3: ECI -> ECEF rotation by GMST about Z axis

def eci_to_ecef(r_eci_m: Tuple[float, float, float], gmst_rad: float) -> Tuple[float, float, float]:
    """
    Rotate a vector from ECI to ECEF via Z-rotation by GMST angle:
      [x_ecef]   [ cosθ  sinθ  0 ] [x_eci]
      [y_ecef] = [-sinθ  cosθ  0 ] [y_eci]
      [z_ecef]   [   0     0   1 ] [z_eci]
    """
    x, y, z = r_eci_m
    cosg = math.cos(gmst_rad)
    sing = math.sin(gmst_rad)
    x_e = cosg * x + sing * y
    y_e = -sing * x + cosg * y
    z_e = z
    return x_e, y_e, z_e



# Step 4: ECEF -> ENU (local East, North, Up)

def ecef_to_enu(r_ecef_m: Tuple[float, float, float], 
                obs_ecef_m: Tuple[float, float, float],
                lat_deg: float, lon_deg: float) -> Tuple[float, float, float]:
    """
    Convert satellite ECEF and observer ECEF to the observer's local-topocentric
    ENU frame (East, North, Up). We first form the line-of-sight vector in ECEF:
        rho_ecef = r_sat_ecef - r_obs_ecef
    and then rotate into ENU using the observer's latitude/longitude.

    ENU rotation matrix (rows are the unit vectors of E, N, U in ECEF coords):
        E = [-sinλ,           cosλ,          0]
        N = [-sinφ cosλ, -sinφ sinλ,  cosφ]
        U = [ cosφ cosλ,  cosφ sinλ,  sinφ]
    """
    lat = d2r(lat_deg)
    lon = d2r(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)

    rx = r_ecef_m[0] - obs_ecef_m[0]
    ry = r_ecef_m[1] - obs_ecef_m[1]
    rz = r_ecef_m[2] - obs_ecef_m[2]

    # East component
    e = -sin_lon * rx + cos_lon * ry
    # North component
    n = -sin_lat * cos_lon * rx - sin_lat * sin_lon * ry + cos_lat * rz
    # Up component
    u = cos_lat * cos_lon * rx + cos_lat * sin_lon * ry + sin_lat * rz

    return e, n, u


# -------------------------------------------------------
# Step 5: ENU -> Azimuth/Elevation/Range
# -------------------------------------------------------
def enu_to_az_el_range(e: float, n: float, u: float) -> Tuple[float, float, float]:
    """
    Compute:
      - range (meters)
      - azimuth (degrees, measured from North going East, wrapped 0..360)
      - elevation (degrees above horizon)
    """
    rng = math.sqrt(e * e + n * n + u * u)
    # atan2(x, y) -> we want Az measured from North toward East, so atan2(E, N)
    az = math.degrees(math.atan2(e, n))
    if az < 0.0:
        az += 360.0
    el = math.degrees(math.asin(u / rng))
    return az, el, rng


# The main function your script calls

def predict_passes(line1: str,
                   line2: str,
                   lat_deg: float | str,
                   lon_deg: float | str,
                   *,
                   alt_m: float = 0.0,
                   start_utc: Optional[datetime] = None,
                   duration_hours: float = 24.0,
                   step_seconds: int = 30
                   ) -> List[PassEvent]:
    """
    Predict visibility passes for a given satellite and observer.

    Parameters
    ----------
    line1, line2 : str
        TLE lines for the satellite (as downloaded to selected_tle).
    lat_deg, lon_deg : float or str
        Observer geodetic latitude/longitude in decimal degrees. (If strings, we convert.)
        Note: tracker.py currently pulls "lat, long" as strings from ipinfo; we handle that.
    alt_m : float
        Observer altitude in meters above mean sea level. Default 0 (good enough).
    start_utc : datetime
        Start time for prediction; defaults to "now" in UTC.
    duration_hours : float
        How far into the future to search for passes.
    step_seconds : int
        Time step between samples; smaller = more precise, but more compute.

    Returns
    -------
    List[PassEvent]
        A list of pass windows (rise, max, set) for the specified horizon (0° elevation).
    """


    # 1) Basic sanitation/conversions
    if isinstance(lat_deg, str):
        lat_deg = float(lat_deg.strip())
    if isinstance(lon_deg, str):
        lon_deg = float(lon_deg.strip())

    # Normalize longitude to [-180, 180] just to be safe
    if lon_deg > 180.0:
        lon_deg -= 360.0
    
    """
    What are the few lines of code above doing?
    -----------------------------------
    If lon_deg is greater than 180° (e.g., 270°E),
    it subtracts 360° → giving the equivalent negative longitude.
    Example:
    Input: lon_deg = 270.0
    Adjustment: 270 - 360 = -90.0
    Meaning: 270°E is the same as 90°W.
    So after this, lon_deg is guaranteed to be within the range [-180°, +180°]
    """

    while True:
        default = input("Do you want to change the default time window of 24 hours. [Y/N] ").strip().lower()
        if default == "y":
            print("\nChanging time window...")
            print("The default setting of a 24 hours time window and a 30 seconds step interval is recommended")
            print("NOTE: A Large time window and a very small step second intervals will lead to larger number of readings.")
            print("Also, a smaller time window and a large step interval may lead to very little to no readings.")
            print("You may miss rise, set, or max elevation with a small window and large step second")
            print("\n___Select Time window___")
            print("1. 3 hours")
            print("2. 6 hours")
            print("3. 12 hours")
            print("4. 24 hours")
            print("5. Custom")
            time_window = input("Choose from 1 - 6: ")
            if time_window == "1":
                print("3 hours time window selected")
                duration_hours = 3.0
                break
            elif time_window == "2":
                print("6 hours time window selected")
                duration_hours = 6.0
                break
            elif time_window == "3":
                print("12 hours time window selected")
                duration_hours = 12.0 
                break
            elif time_window == "4":
                print("24 hours time window selected")
                duration_hours = 48.0
                break
            elif time_window == "5":
                while True:
                    custom = input("Enter custom time window in hours (e.g., 5.5 for 5 hours 30 minutes): ").strip()
                    try:
                        duration_hours = float(custom)
                        if duration_hours <= 0:
                            print("Please enter a positive number for hours.")
                            continue
                        print(f"Custom time window of {duration_hours} hours selected.")
                        break
                    except ValueError:
                        print("Invalid input. Please enter a numeric value for hours.")
                        continue
                break
            else:
                print("Please choose a valid option from 1 - 5")
                continue
        elif default == "n":
            print("No change in default time of 24 hours")
            break
        else:
            print("Please choose Y or N! ")
            continue


    while True:
        step = input("\nDo you want to change the default step interval of 30 seconds? [Y/N] ").strip().lower()
        if step == "y":
            print("\nChanging step interval...")
            print("The default setting of 30 seconds step interval is recommended")
            print("NOTE: A very small step second intervals will lead to larger number of readings.")
            print("Also, a large step interval may lead to very little to no readings.")
            print("You may miss rise, set, or max elevation with a large step second")
            print("\n___Select Step Interval___")
            print("1. 10 seconds")
            print("2. 20 seconds")
            print("3. 45 seconds")
            print("4. 60 seconds")
            print("5. Custom")
            step_interval = input("Choose from 1 - 5: ")
            if step_interval == "1":
                print("10 seconds step interval selected")
                step_seconds = 10
                break
            elif step_interval == "2":
                print("20 seconds step interval selected")
                step_seconds = 20
                break
            elif step_interval == "3":
                print("45 seconds step interval selected")
                step_seconds = 45
                break
            elif step_interval == "4":
                print("60 seconds step interval selected")
                step_seconds = 60
                break
            elif step_interval == "5":
                while True:
                    custom_step = input("Enter custom step interval in seconds (e.g., 15): ").strip()
                    try:
                        step_seconds = int(custom_step)
                        if step_seconds <= 0:
                            print("Please enter a positive integer for seconds.")
                            continue
                        print(f"Custom step interval of {step_seconds} seconds selected.")
                        break
                    except ValueError:
                        print("Invalid input. Please enter an integer value for seconds.")
                        continue
                break
            else:
                print("Please choose a valid option from 1 - 5")
                continue
        elif step == "n":
             print("No change in default step interval of 30 secs")
             break
            
        else:
            print("Select a valid option")
            continue



    # Use current UTC time if not specified
    if start_utc is None:
        start_utc = datetime.now(timezone.utc)

    # Build the sgp4 satellite object from TLE
    sat = Satrec.twoline2rv(line1.strip(), line2.strip())

    # Pre-compute observer ECEF (constant)
    obs_ecef_m = geodetic_to_ecef(lat_deg, lon_deg, alt_m)

    # Storage for pass detection
    passes: List[PassEvent] = []

    # State for the current pass being tracked
    in_view = False
    rise_time = None
    rise_az = None
    max_el = -999.0
    max_time = None

    # We'll scan over the requested time window
    t = start_utc
    end_utc = start_utc + timedelta(hours=duration_hours)

    # Previous elevation to detect horizon crossings (sign changes around 0°)
    prev_el = None
    prev_az = None
    prev_t = None

    while t <= end_utc:
        # 2) Propagate satellite to time t using sgp4
        # sgp4 expects Julian date/fraction:
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond * 1e-6)
        error_code, r_eci_km, v_eci_km_s = sat.sgp4(jd, fr)
        if error_code != 0:
            # If sgp4 reports an error (e.g., decay), we skip this timestamp safely
            # This can also be logged/printed
            t += timedelta(seconds=step_seconds)
            continue

        # Convert km -> meters for consistent units
        r_eci_m = (r_eci_km[0] * 1000.0, r_eci_km[1] * 1000.0, r_eci_km[2] * 1000.0)

        # 3) Rotate ECI -> ECEF using GMST
        theta_g = gmst_angle(t)
        r_ecef_m = eci_to_ecef(r_eci_m, theta_g)

        # 4) Observer-topocentric vector (in ENU) and angles
        e, n, u = ecef_to_enu(r_ecef_m, obs_ecef_m, lat_deg, lon_deg)
        az, el, rng_m = enu_to_az_el_range(e, n, u)

        # 5) Pass detection logic (elevation crossing 0°)
        if prev_el is not None:
            # Detect rising edge: went from below horizon to above
            if prev_el <= 0.0 and el > 0.0 and not in_view:
                in_view = True
                rise_time = t
                rise_az = az
                max_el = el
                max_time = t

            # Track max elevation while in view
            if in_view and el > max_el:
                max_el = el
                max_time = t

            # Detect setting edge: goes back below or equal to 0°
            if in_view and el <= 0.0:
                # We just ended a pass; record it.
                set_time = t
                set_az = az
                passes.append(PassEvent(
                    rise_time_utc=rise_time,
                    max_time_utc=max_time,
                    max_elevation_deg=max_el,
                    set_time_utc=set_time,
                    rise_azimuth_deg=rise_az,
                    set_azimuth_deg=set_az
                ))
                # Reset state
                in_view = False
                rise_time = None
                rise_az = None
                max_el = -999.0
                max_time = None

        # Save previous sample for next iteration
        prev_el = el
        prev_az = az
        prev_t = t

        # Advance time
        t += timedelta(seconds=step_seconds)

    # If we ended the loop while still in view (rare), close the pass at end_utc
    if in_view and rise_time is not None and max_time is not None:
        passes.append(PassEvent(
            rise_time_utc=rise_time,
            max_time_utc=max_time,
            max_elevation_deg=max_el,
            set_time_utc=end_utc,
            rise_azimuth_deg=rise_az if rise_az is not None else 0.0,
            set_azimuth_deg=prev_az if prev_az is not None else 0.0
        ))

    # Print a friendly summary if there is no view in the user's selected window
    if not passes:
        print("No visible passes in the specified window.")
    else:
        print("\nPredicted passes (UTC):")
        print("------------------------------------------------------------")
        print("Pass |   Day    | Time | Para.| Angle |")
        print("------------------------------------------------------------")
        for p in passes:
            print(f"Rise: {p.rise_time_utc.strftime('%Y-%m-%d %H:%M:%S')}  "
                  f"Az {p.rise_azimuth_deg:6.1f}°")
            print(f" Max: {p.max_time_utc.strftime('%Y-%m-%d %H:%M:%S')}  "
                  f"El {p.max_elevation_deg:6.1f}°")
            print(f" Set: {p.set_time_utc.strftime('%Y-%m-%d %H:%M:%S')}  "
                  f"Az {p.set_azimuth_deg:6.1f}°")
            print("------------------------------------------------------------")

    return passes


# -------------------------------------------------------
# Optional: quick CLI test if you run this file directly
# -------------------------------------------------------
if __name__ == "__main__":
    # This block lets you run:  python predictor.py
    # It will try to read "selected_tle" and predict passes for Kigali by default.
    import os
    default_lat = -1.95
    default_lon = 30.06

    tle_path = "selected_tle.txt"
    if not os.path.exists(tle_path):
        print("Could not find 'selected_tle.txt'. Please run your fetch script first.")
        raise SystemExit(1)

    with open(tle_path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]

    if len(lines) < 3:
        print("The Selected Satellite has issues with thier essential files.\nTry again).")
        raise SystemExit(1)

    sat_name = lines[0]
    l1, l2 = lines[1], lines[2]
    print(f"Predicting passes for {sat_name}")

    predict_passes(l1, l2, default_lat, default_lon,
                   duration_hours=24.0,
                   step_seconds=10)





