#!/usr/bin/env python3
"""
validate.py - Helm config validation
"""

import argparse
import logging
import sys
import yaml
from collections import defaultdict
from typing import List, Optional, Tuple
import tempfile
import subprocess

RESOURCE_TYPES = defaultdict(lambda: {
        "clusters": str,
        "projects": {
            "TYPE_SCOPE": "global",
            "buckets": str,
        }
    }, 
    {
        "iac": {
            "iac-role-bindings": list,
        },
        "global": {
            "iam-roles": str,
            "projects": {
                "iam-roles": str,
                "iam-role-bindings": list,
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


def resource_config(resource_type: str, obj: dict, parents: list[dict]) -> dict:
    parent = parents[-1]
    if resource_type == "buckets":
        return {resource_type.replace("-",""): [{**obj, 
                'namespace': parent.get('name'),
                'location': obj.get('location', parents[0].get('name'))
                }]}
    if resource_type == "iam-role-bindings":
        return {'namespace': parent.get('name'), resource_type.replace("-",""): obj}
    return {resource_type.replace("-",""): [obj]}

    
def release_name(resource_type: str, obj: dict | list, parents: list[dict]) -> str:
    parent = parents[-1]
    if isinstance(obj, list):
        return f"{parent.get('name','root')}-{resource_type}"
    return f"{parent.get('name','root')}-{resource_type}-{obj.get('name','root')}"


def action_cmd(action: str, release_name: str = None, chart: str = None, values_file: str = None, extra_args: list[str] = None) -> list[str]:
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        cmd = ["helm", "--debug"]
    else:
        cmd = ["helm"]
    
    if action == "list":
        cmd.extend(["list"])
    elif action == "template":
        cmd.extend(["template", release_name, chart, "-f", values_file])
    elif action == "upgrade":
        cmd.extend(["upgrade", "--install", release_name, chart, "-f", values_file])
    elif action == "install":
        cmd.extend(["install", release_name, chart, "-f", values_file])
    elif action == "lint":
        cmd.extend(["lint", chart, "-f", values_file])
    elif action == "show":
        cmd.extend(["show", "all", chart])
    elif action in ["uninstall", "delete"]:
        cmd.extend(["uninstall", release_name])
    elif action in ["status", "test", "history", "rollback"]:
        cmd.extend([action, release_name])
    elif action.startswith("get "):
        cmd.extend(action.split() + [release_name])
    else:
        raise ValueError(f"Invalid action: {action}")
    cmd.extend(extra_args)
    return cmd


def call_global_action(action: str, dry_run: bool, extra_args: list[str]) -> None:
    cmd = action_cmd(action=action, extra_args=extra_args)
    logging.info(f"{' '.join(cmd)}")
    if not dry_run:
        try:
            output = subprocess.check_output(cmd, text=True)
            logging.info(output)
            if output:
                logging.info(output)
        except subprocess.CalledProcessError as e:
            logging.error(f"Helm failed with return code {e.returncode}")
            logging.error(f"Error output (if captured): {e.output}")
        except FileNotFoundError as e:
            logging.error(f"Error: Helm not found or could not be executed. {e}")


def call_resource_action(action: str, resource_type: str, obj: dict | list, parents: list[dict], extra_args: list[str]) -> None:
    parent = parents[-1]
    release = release_name(resource_type, obj, parents)
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as tmp:
            values_yaml = yaml.safe_dump(resource_config(resource_type, obj, parents))
            logging.debug(values_yaml)
            tmp.write(values_yaml)
            tmp.flush()
            cmd = action_cmd(action, release, f"../../charts/gdc-{resource_type}", tmp.name, extra_args)
            logging.info(f"{' '.join(cmd)}")
            output = subprocess.check_output(cmd, text=True) 
            logging.info(f"Helm {action} {release} finished")
            if output:
                logging.info(output)
    except subprocess.CalledProcessError as e:
            logging.error(f"Helm failed with return code {e.returncode}")
            logging.error(f"Error output (if captured): {e.output}")
    except FileNotFoundError as e:
            logging.error(f"Error: Helm not found or could not be executed. {e}")


def process_type(action: str, type_path: str, resource_type: str, type_tree: dict | type, config: dict, dry_run: bool, parents: list[dict], extra_args: list[str]) -> None:
    logging.debug(f"process_type {type_path}/{resource_type}")
    parent = parents[-1]
    if resource_type not in config:
        return
    if type_tree is list:
        logging.debug(f"{action} list {parent.get('name', type_path)}/{resource_type}")
        obj = config[resource_type]
        if not dry_run:
            call_resource_action(action, resource_type, obj, parents, extra_args)
        return
    if type_tree is str:
        for i, obj in enumerate(config[resource_type]):
            logging.debug(f"{action} object {parent.get('name', type_path)}/{resource_type}/{obj.get('name',obj)}")
            if not dry_run:
                call_resource_action(action, resource_type, obj, parents, extra_args)
            return
    for i, obj in enumerate(config[resource_type]):
        logging.debug(f"{action} object {parent.get('name', type_path)}/{resource_type}/{obj.get('name',obj)}")
        resource_scope = type_tree.get("TYPE_SCOPE", parent.get("name", type_path))
        skip_helm = dry_run
        if resource_scope != parent.get("name", type_path):
            skip_helm = True
        if not skip_helm:
            call_resource_action(action, resource_type, obj, parents, extra_args)
        for t, v in type_tree.items():
            parents.append(obj)
            process_type(action, f"{type_path}/{resource_type}", t, v, config[resource_type][i], dry_run, parents, extra_args)


def process(config: dict, action: str, dry_run: bool, extra_args: list[str]) -> bool:
    """
    Performs the logic.

    Args:
        config: Configuration object

    Returns:
        True if validation succeeds, False otherwise.
    """

    for api in config:
        for t, v in RESOURCE_TYPES[api].items():
            process_type(action, api, t, v, config[api], dry_run, [{'name': api}], extra_args)
    return True


def parse_args(args: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Validation CLI Tool")

    parser.add_argument(
        "action",
        help="Action to perform",
        type=str
    )

    parser.add_argument(
        "config",
        help="Path to configuration file",
        type=str,
        nargs="?"
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

    return parser.parse_known_args(args)


def main() -> int:
    args, extra_args = parse_args(sys.argv[1:])
    setup_logging(args.verbose)
    if args.config:
        with open(args.config, "r") as f:
            logging.info(f"Processing file {args.config}")
            config = yaml.safe_load(f)
            process(config, args.action, args.dry_run, extra_args)
    else:
        call_global_action(
            action=args.action, 
            dry_run=args.dry_run, 
            extra_args=extra_args
        )


if __name__ == "__main__":
    sys.exit(main())