"""Command line interface.

Subcommands::

    mosaic validate <pipeline.yaml>      # parse and validate the YAML file
    mosaic run      <pipeline.yaml>      # execute the pipeline
    mosaic inspect  <output.zarr>        # print store summary
    mosaic prov     show <stac.json>     # print provenance highlights
    mosaic sources  list                 # list registered source plugins

The CLI is built on Typer. We keep it deliberately small because the canonical
interface for reproducible runs is the YAML file.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from mosaic._spec import PipelineSpec
from mosaic.runner import run as runner_run
from mosaic.sources.base import registry

app = typer.Typer(no_args_is_help=True, add_completion=False, help="MOSAIC command line.")
prov_app = typer.Typer(help="Inspect provenance artefacts.")
sources_app = typer.Typer(help="Inspect registered source plugins.")
app.add_typer(prov_app, name="prov")
app.add_typer(sources_app, name="sources")

console = Console()


@app.command("validate")
def validate(pipeline_file: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Validate a pipeline YAML file against the schema."""
    spec = PipelineSpec.from_yaml(pipeline_file)
    console.print(f"[green]OK[/green] {pipeline_file}: pipeline '{spec.metadata.name}' is valid.")


@app.command("run")
def run_cmd(pipeline_file: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Run a pipeline declared in a YAML file."""
    result = runner_run(pipeline_file)
    summary = result.to_summary()
    table = Table(title=f"MOSAIC run: {result.provenance.id}")
    table.add_column("key", style="bold")
    table.add_column("value")
    for k, v in summary.items():
        table.add_row(k, str(v))
    console.print(table)


@app.command("inspect")
def inspect(store_path: Path = typer.Argument(..., exists=True)) -> None:
    """Print a brief summary of a Zarr/NetCDF output."""
    import xarray as xr

    if store_path.suffix == ".zarr" or store_path.is_dir():
        ds = xr.open_zarr(store_path, consolidated=True)
    else:
        ds = xr.open_dataset(store_path)
    console.print(ds)


@prov_app.command("show")
def prov_show(stac_file: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Show key provenance fields from a STAC sidecar JSON."""
    payload = json.loads(stac_file.read_text(encoding="utf-8"))
    props = payload.get("properties", {})
    table = Table(title=f"Provenance: {payload.get('id', stac_file.name)}")
    table.add_column("key", style="bold")
    table.add_column("value")
    for k in (
        "mosaic:pipeline_hash",
        "mosaic:content_hash",
        "processing:software",
        "mosaic:harmonization",
        "mosaic:qc",
    ):
        if k in props:
            table.add_row(k, json.dumps(props[k]))
    console.print(table)


@sources_app.command("list")
def sources_list() -> None:
    """List registered source plugins."""
    table = Table(title="Registered MOSAIC source plugins")
    table.add_column("plugin", style="bold")
    table.add_column("class")
    for name in registry.names():
        cls = registry.get(name)
        table.add_row(name, f"{cls.__module__}.{cls.__qualname__}")
    console.print(table)


def main() -> None:  # pragma: no cover - thin wrapper for entry point
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
