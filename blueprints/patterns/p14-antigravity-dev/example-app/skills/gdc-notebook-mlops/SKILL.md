---
name: gdc-notebook-mlops
description: Structured Jupyter Notebook (.ipynb v4) cell inspection, editing, execution, magic commands, and KFP/Papermill pipeline export.
---

# GDC Integrated Notebooks & MLOps Skill (`gdc-notebook-mlops`)

Use this skill when inspecting, authoring, debugging, or refactoring Jupyter Notebooks (`.ipynb`) inside the `p14-antigravity-dev` workspace (`/home/dev/workspace`).

## 1. Structured `.ipynb` Cell Operations (Never Corrupt Raw JSON)

Always use the structured cell tools rather than raw text diffs on `.ipynb` files:
- `notebook_list_cells(notebook_path)`: Lists all cells with 0-based `cell_index`, `cell_type` (`code` or `markdown`), `execution_count`, full `source`, `stdout`, and `error_summary`.
- `notebook_get_cell_outputs(notebook_path, cell_index)`: Returns the full cell source, stdout/stderr streams, `execute_result` payloads, and Python exception tracebacks (`ename`, `evalue`, `traceback`).
- `notebook_add_cell(notebook_path, new_source="", cell_type="code", insert_index=-1)`: Creates a `.ipynb.bak` backup and appends or inserts a new `code` or `markdown` cell.
- `notebook_edit_cell(notebook_path, cell_index, new_source, cell_type="code")`: Creates a `.ipynb.bak` backup and updates or inserts a single cell while preserving notebook metadata (`kernelspec`, `nbformat=4`).
- `notebook_delete_cell(notebook_path, cell_index)`: Creates a `.ipynb.bak` backup and deletes the cell at `cell_index` while preserving at least 1 cell in the notebook.
- `notebook_run_cell(notebook_path, cell_index)`: Executes a specific code cell in the workspace Python environment with a scrubbed `SAFE_ENV` and records structured outputs back into the `.ipynb` cell.
- `notebook_rollback_cell(notebook_path)`: Restores the `.ipynb` notebook from its `.ipynb.bak` snapshot.

## 2. IPython Antigravity Cell Magics (`%%agy_*`)

Notebooks in `/lab/` can load `gdc_antigravity_magic` (`%load_ext gdc_antigravity_magic`) to invoke the Antigravity SDK Swarm inline:
- `%%agy_architect`: Generates a `BlueprintAdaptationPlan` and architectural markdown summary right inside the notebook output.
- `%%agy_builder <target_file_or_notebook>`: Proposes surgical code/cell changes with HITL approval.
- `%%agy_verify`: Runs `pytest`, `helm lint`, or `kubectl apply --dry-run=client` verification checks.
