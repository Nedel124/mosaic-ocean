from pathlib import Path

import matplotlib.pyplot as plt
import xarray as xr

zarr_path = "out/cs1_gulf_of_riga_upwelling_offline.zarr"
fig_dir = Path("figures")
fig_dir.mkdir(exist_ok=True)

ds = xr.open_zarr(zarr_path, consolidated=False)
print(ds)

date = "2021-07-16"

# SST
plt.figure(figsize=(7, 5))
ds["sea_surface_temperature"].sel(time=date).plot()
plt.title("CS1 Gulf of Riga — SST, 16 July 2021")
plt.tight_layout()
plt.savefig(fig_dir / "fig_cs1_gulf_of_riga_sst_2021-07-16.png", dpi=300)
plt.close()

# SST spatial anomaly
plt.figure(figsize=(7, 5))
ds["sst_spatial_anomaly"].sel(time=date).plot()
plt.title("CS1 Gulf of Riga — spatial SST anomaly, 16 July 2021")
plt.tight_layout()
plt.savefig(fig_dir / "fig_cs1_gulf_of_riga_sst_spatial_anomaly_2021-07-16.png", dpi=300)
plt.close()

# SST-only mask
plt.figure(figsize=(7, 5))
ds["upwelling_mask_sst"].sel(time=date).plot()
plt.title("CS1 Gulf of Riga — SST-only upwelling mask, 16 July 2021")
plt.tight_layout()
plt.savefig(fig_dir / "fig_cs1_gulf_of_riga_mask_sst_2021-07-16.png", dpi=300)
plt.close()

# SST + wind mask
plt.figure(figsize=(7, 5))
ds["upwelling_mask_sst_wind"].sel(time=date).plot()
plt.title("CS1 Gulf of Riga — pixel-wise SST–wind mask, 16 July 2021")
plt.tight_layout()
plt.savefig(fig_dir / "fig_cs1_gulf_of_riga_mask_sst_wind_2021-07-16.png", dpi=300)
plt.close()

# Time series liczby komórek
sst_cells = ds["upwelling_mask_sst"].astype("uint8").sum(dim=("latitude", "longitude"))
joint_cells = ds["upwelling_mask_sst_wind"].astype("uint8").sum(dim=("latitude", "longitude"))

plt.figure(figsize=(8, 4))
sst_cells.plot(label="SST-only mask")
joint_cells.plot(label="SST–wind intersection")
plt.legend()
plt.title("CS1 Gulf of Riga — flagged cells over time")
plt.ylabel("Number of flagged cells")
plt.tight_layout()
plt.savefig(fig_dir / "fig_cs1_gulf_of_riga_flagged_cells_timeseries.png", dpi=300)
plt.close()

print("Saved figures to:", fig_dir.resolve())
print(
    "SST-mask cells on",
    date,
    ":",
    int(ds["upwelling_mask_sst"].sel(time=date).astype("uint8").sum()),
)
print(
    "SST-wind cells on",
    date,
    ":",
    int(ds["upwelling_mask_sst_wind"].sel(time=date).astype("uint8").sum()),
)
