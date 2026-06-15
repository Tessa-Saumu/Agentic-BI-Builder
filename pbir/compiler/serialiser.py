"""
Serialiser — writes PBIRProject model to the correct .pbip folder layout:
  report.pbip/
    definition/
      pages/        one JSON per page
      visuals/      visual definitions
      expressions/  DAX measures
      model.json    data model + table schema
      connections.json  data source connection
"""
import json
from pathlib import Path
from pbir.models.project import PBIRProject


def write_pbip(project: PBIRProject, output_dir: Path) -> None:
    # TODO: create folder tree and write JSON files
    raise NotImplementedError
