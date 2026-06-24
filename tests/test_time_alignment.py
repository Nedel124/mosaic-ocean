import pandas as pd
import xarray as xr

from mosaic.runner import _apply_time_alignment


def test_daily_mean_time_alignment() -> None:
    ds = xr.Dataset(
        {
            "eastward_wind": (
                ("time",),
                [1.0, 3.0, 5.0, 7.0],
            )
        },
        coords={
            "time": pd.to_datetime(
                [
                    "2021-07-16T00:00:00",
                    "2021-07-16T06:00:00",
                    "2021-07-16T12:00:00",
                    "2021-07-16T18:00:00",
                ]
            )
        },
    )

    result = _apply_time_alignment(ds, "daily_mean")

    assert result.sizes["time"] == 1
    assert float(result["eastward_wind"].values[0]) == 4.0
