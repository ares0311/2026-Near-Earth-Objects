"""
Diagnostic script: probe the IRSA NEOWISE query directly with full error reporting.
Run with: PYTHONPATH=src uv run python <this_file>
"""
import sys

print("--- Step 1: Import astroquery ---", flush=True)
try:
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.ipac.irsa import Irsa
    print("  OK", flush=True)
except ImportError as e:
    print(f"  IMPORT ERROR: {e}", flush=True)
    sys.exit(1)

ra, dec, radius = 58.0, 20.0, 3.5
catalog = "neowiser_p1bs_psd"
coord = SkyCoord(ra=ra, dec=dec, unit="deg")

print(f"--- Step 2: Query IRSA catalog={catalog} at RA={ra} Dec={dec} r={radius}° ---", flush=True)
try:
    table = Irsa.query_region(
        coord,
        catalog=catalog,
        spatial="Cone",
        radius=radius * u.deg,
    )
    n = len(table) if table is not None else "None"
    print(f"  Query returned: type={type(table)}, len={n}", flush=True)
    if table is not None and len(table) > 0:
        print(f"  Columns: {table.colnames}", flush=True)
        print(f"  First row: {dict(zip(table.colnames, table[0]))}", flush=True)
        # Check MJD window
        start_jd, end_jd = 2458880.5, 2458910.5
        start_mjd = start_jd - 2_400_000.5
        end_mjd = end_jd - 2_400_000.5
        print(f"  MJD filter: {start_mjd:.1f} to {end_mjd:.1f}", flush=True)
        # Try to find the epoch column
        epoch_col = None
        for candidate in ("mjd", "mjd_obs", "mjd_obs_w1", "date_obs"):
            if candidate in table.colnames:
                epoch_col = candidate
                break
        print(f"  Epoch column detected: {epoch_col}", flush=True)
        if epoch_col:
            in_window = sum(
                1 for row in table if start_mjd <= float(row[epoch_col]) <= end_mjd
            )
            print(f"  Rows in MJD window: {in_window} / {len(table)}", flush=True)
            mjds = [float(row[epoch_col]) for row in table]
            print(f"  MJD range in table: {min(mjds):.1f} to {max(mjds):.1f}", flush=True)
        else:
            print(f"  WARNING: no epoch column found in {table.colnames}", flush=True)
    else:
        print("  Table is empty or None.", flush=True)
except Exception as exc:
    print(f"  EXCEPTION: {type(exc).__name__}: {exc}", flush=True)

print("--- Done ---", flush=True)
