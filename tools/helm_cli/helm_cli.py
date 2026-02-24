#!/usr/bin/env python3
"""
helm_cli.py - Helm config validation
python3 helm_cli.py /mnt/c/temp/DGA/Repo/examples/multi-value-org/d2-user.yaml --dry-run -v
python3 helm_cli.py /mnt/c/temp/DGA/Repo/examples/multi-value-org/d4-shared.yaml --dry-run -v

"""

import argparse
import logging
import sys
import yaml
from collections import defaultdict
from typing import List, Optional
import tempfile
import subprocess

RESOURCE_TYPES = defaultdict(lambda: {
        "clusters": str,
        "projects": {
            "buckets": str,
        }
    }, 
    {
        "iac": {
            "iac-role-bindings": str,
        },
        "global": {
            "iam-roles": str,
            "iam-roles": str,
            "projects": {
                "iam-roles": str,
                "iam-role-bindings": str,
            }
        },
    })

def setup_logging(verbose: bool = False) -> None:
    """Configures the logging settings."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def resource_config(resource_type: str, obj: dict, parent: Optional[dict] = None) -> dict:
    match resource_type:
        case "buckets":
            return {resource_type.replace("-",""): [{**obj, 'namespace': parent.get('name')}]}
        case "iam-role-bindings":
            return {'namespace': parent.get('name'), resource_type.replace("-",""): [obj]}
        case _:
            return {resource_type.replace("-",""): [obj]}

    


def resource_config(resource_type: str, obj: dict, parent: Optional[dict] = None) -> dict:
    match resource_type:
        case "buckets":
            return {resource_type.replace("-",""): [{**obj, 'namespace': parent.get('name')}]}
        case "iam-role-bindings":
            return {'namespace': parent.get('name'), resource_type.replace("-",""): [obj]}
        case _:
            return {resource_type.replace("-",""): [obj]}

    

def call_helm(action: str, resource_type: str, obj: dict, parent: Optional[dict] = None) -> None:
    release_name = f"{resource_type}-{obj.get('name','root')}"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as tmp:
            values_yaml = yaml.safe_dump(resource_config(resource_type, obj, parent))
            logging.debug(values_yaml)
            tmp.write(values_yaml)
            tmp.flush()
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                cmd = ["helm", "--debug", action, release_name, f"../../charts/gdc-{resource_type}", "-f", tmp.name]
            else:
                cmd = ["helm", action, release_name, f"../../charts/gdc-{resource_type}", "-f", tmp.name]
            logging.info(f"{' '.join(cmd)}")
            output = subprocess.check_output(cmd, text=True) 
            logging.info(f"Helm {action} {release_name} finished")
            if output:
                logging.info(output)
    except subprocess.CalledProcessError as e:
            logging.error(f"Helm failed with return code {e.returncode}")
            logging.error(f"Error output (if captured): {e.output}")
            logging.error(f"Helm failed with return code {e.returncode}")
            logging.error(f"Error output (if captured): {e.output}")
    except FileNotFoundError as e:
            logging.error(f"Error: Helm not found or could not be executed. {e}")
            logging.error(f"Error: Helm not found or could not be executed. {e}")


def process_type(action: str, type_path: str, resource_type: str, type_tree: Union[dict, type], config: dict, dry_run: bool, parent: Optional[dict] = None) -> None:
    logging.debug(f"process_type {type_path}/{resource_type}")
    if resource_type not in config:
        return
    for i, obj in enumerate(config[resource_type]):
        if parent:
            logging.debug(f"{action} object {type_path}/{parent.get('name',parent)}/{resource_type}/{obj.get('name',obj)}")
        else:
            logging.debug(f"{action} object {type_path}/{resource_type}/{obj.get('name',obj)}")
        if not dry_run:
            call_helm(action, resource_type, obj, parent)
        if isinstance(type_tree, dict):
            for t, v in type_tree.items():
                process_type(action, f"{type_path}/{resource_type}", t, v, config[resource_type][i], dry_run, obj)


def process(config: str, action: str, dry_run: bool) -> bool:
    """
    Performs the logic.

    Args:
        config: Configuration object

    Returns:
        True if validation succeeds, False otherwise.
    """

    for api in config:
        for t, v in RESOURCE_TYPES[api].items():
            process_type(action, api, t, v, config[api], dry_run)
    return True


def parse_args(args: List[str]) -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Validation CLI Tool")

    parser.add_argument(
        help="Path to configuration file",
        type=str,
        dest="config"
    )

    parser.add_argument(
        "-a", "--action",
        default="template",
        help="Action to perform",
        type=str
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser.parse_args(args)


def main() -> int:
    args = parse_args(sys.argv[1:])
    setup_logging(args.verbose)
    with open(args.config, "r") as f:
        logging.info(f"Processing file {args.config}")
        config = yaml.safe_load(f)
        process(config, args.action, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())