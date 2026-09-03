"""
Utility script to export Pydantic models as standard JSON Schema files (.json).
Useful for non-Python services, documentation, and schema registries.
"""

import json
from pathlib import Path
from event_contracts.events import CaseCreatedEvent, CaseStatusChangedEvent


def export_all_schemas(output_dir: Path | None = None) -> None:
    """Export JSON Schema files to the schemas/ directory."""
    if output_dir is None:
        output_dir = Path(__file__).parent / "schemas"
    output_dir.mkdir(parents=True, exist_ok=True)

    schemas = {
        "case.created.schema.json": CaseCreatedEvent.model_json_schema(),
        "case.status.changed.schema.json": CaseStatusChangedEvent.model_json_schema(),
    }

    for filename, schema_dict in schemas.items():
        file_path = output_dir / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(schema_dict, f, indent=2)
        print(f"Exported JSON schema to: {file_path}")


if __name__ == "__main__":
    export_all_schemas()
