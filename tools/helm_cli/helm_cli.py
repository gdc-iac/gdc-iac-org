#!/usr/bin/env python3
"""
validate.py - Helm config validation
"""

import argparse
import logging
import subprocess
import sys
import tempfile
from collections import defaultdict
from typing import List, Tuple, Union

import yaml

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
        }
})


def setup_logging(verbose: bool = False) -> None:
    """Configures the logging settings."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def resource_config(
    resource_type: str, obj: dict, parents: List[dict]
) -> dict:
    """
    Constructs the configuration dictionary for a specific resource type.

    Args:
        resource_type: The type of the resource (e.g., 'buckets').
        obj: The resource properties dictionary.
        parents: A list of parent objects providing context (e.g. namespaces).

    Returns:
        A dictionary representing the transformed config for the resource.
    """
    parent = parents[-1]
    if resource_type == "buckets":
        return {"buckets": [{
            **obj,
            'namespace': parent.get('name'),
            'location': obj.get('location', parents[0].get('name'))
        }]}
    if resource_type == "iam-role-bindings":
        return {
            'namespace': parent.get('name'),
            'iamrolebindings': obj
        }
    return {resource_type.replace("-", ""): [obj]}


def release_name(
    resource_type: str, obj: Union[dict, list], parents: List[dict]
) -> str:
    """
    Generates a standardized Helm release name for a resource.

    Args:
        resource_type: The type of the resource.
        obj: The resource object or list of objects.
        parents: Contextual parent objects.

    Returns:
        A formatted string to be used as the Helm release name.
    """
    parent = parents[-1]
    if isinstance(obj, list):
        return f"{parent.get('name', 'root')}-{resource_type}"
    parent_name = parent.get('name', 'root')
    obj_name = obj.get('name', 'root')
    return f"{parent_name}-{resource_type}-{obj_name}"


def action_cmd(
    action: str,
    release_name: str = None,
    chart: str = None,
    values_file: str = None,
    extra_args: List[str] = None
) -> List[str]:
    """
    Constructs the corresponding helm command line for a given action.

    Args:
        action: The helm action to perform (e.g., 'upgrade', 'template').
        release_name: The name of the helm release (optional).
        chart: The path to the local helm chart (optional).
        values_file: The path to the values YAML file (optional).
        extra_args: Any extra arguments to append to the command (optional).

    Returns:
        A list of strings representing the helm command to execute.

    Raises:
        ValueError: If an unsupported action is provided.
    """
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        cmd = ["helm", "--debug"]
    else:
        cmd = ["helm"]

    if action == "list":
        cmd.extend(["list"])
    elif action == "template":
        cmd.extend(["template", release_name, chart, "-f", values_file])
    elif action == "upgrade":
        cmd.extend(["upgrade", "--install", release_name,
                   chart, "-f", values_file])
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


def call_global_action(
    action: str, dry_run: bool, extra_args: List[str]
) -> None:
    """
    Executes a global helm action (e.g., 'list') that does not require a chart.

    Args:
        action: The helm action to perform.
        dry_run: If True, skips actual execution and only logs.
        extra_args: Extra arguments to append to the command.
    """
    cmd = action_cmd(action=action, extra_args=extra_args)
    logging.info(f"{' '.join(cmd)}")
    if not dry_run:
        try:
            output = subprocess.check_output(cmd, text=True)
            if output:
                logging.info(output)
        except subprocess.CalledProcessError as e:
            logging.error(f"Helm failed with return code {e.returncode}")
            logging.error(f"Error output (if captured): {e.output}")
        except FileNotFoundError as e:
            logging.error(
                f"Error: Helm not found or could not be executed. {e}")


def call_resource_action(
    action: str, resource_type: str, obj: Union[dict, list],
    parents: List[dict], extra_args: List[str]
) -> None:
    """
    Executes a helm action for a specific resource.

    It creates a temporary YAML values file for the resource config and
    invokes helm with the proper chart and release name.

    Args:
        action: The helm action to perform.
        resource_type: The type of the resource.
        obj: The resource object or list.
        parents: The parent context.
        extra_args: Extra arguments for the helm command.
    """
    release = release_name(resource_type, obj, parents)
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as tmp:
            values_yaml = yaml.safe_dump(
                resource_config(resource_type, obj, parents))
            logging.debug(values_yaml)
            tmp.write(values_yaml)
            tmp.flush()
            cmd = action_cmd(
                action, release, f"../../charts/gdc-{resource_type}",
                tmp.name, extra_args
            )
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


def process_type(
    action: str,
    type_path: str,
    resource_type: str,
    type_tree: Union[dict, type],
    config: dict,
    dry_run: bool,
    parents: List[dict],
    extra_args: List[str]
) -> None:
    """
    Recursively processes a node in the resource tree configuration.

    Args:
        action: The action to perform on each resource.
        type_path: The logical path of the resource type.
        resource_type: The current resource type being processed.
        type_tree: The nested tree structure defining resource relationships.
        config: The extracted configuration fragment.
        dry_run: If True, prints actions without executing them.
        parents: A list of parent nodes accumulating context.
        extra_args: Extra arguments to pass down to helm executions.
    """
    logging.debug(f"process_type {type_path}/{resource_type}")
    parent = parents[-1]
    if resource_type not in config:
        return
    if type_tree is list: #generate one release per object list
        logging.debug(
            f"{action} list {parent.get('name', type_path)}/{resource_type}")
        obj = config[resource_type]
        if not dry_run:
            call_resource_action(action, resource_type,
                                 obj, parents, extra_args)
        return
    if type_tree is str: #generate one release per object
        for i, obj in enumerate(config[resource_type]):
            parent_name = parent.get('name', type_path)
            obj_name = obj.get('name', obj)
            logging.debug(
                f"{action} object {parent_name}/{resource_type}/{obj_name}"
            )
            if not dry_run:
                call_resource_action(action, resource_type,
                                     obj, parents, extra_args)
        return
    for i, obj in enumerate(config[resource_type]):
        parent_name = parent.get('name', type_path)
        obj_name = obj.get('name', obj)
        logging.debug(
            f"{action} object {parent_name}/{resource_type}/{obj_name}"
        )
        resource_scope = type_tree.get(
            "TYPE_SCOPE", parent.get("name", type_path))
        skip_helm = dry_run
        if resource_scope != parent.get("name", type_path):
            skip_helm = True
        if not skip_helm:
            call_resource_action(action, resource_type,
                                 obj, parents, extra_args)
        for t, v in type_tree.items():
            parents.append(obj)
            process_type(
                action, f"{type_path}/{resource_type}", t, v,
                config[resource_type][i], dry_run, parents, extra_args
            )


def process(
    config: dict, action: str, dry_run: bool, api: str, extra_args: List[str]
) -> bool:
    """
    Entry point for traversing the configuration dictionary
    and validating APIs.

    Args:
        config: The complete configuration dictionary loaded from YAML.
        action: The helm action to perform (e.g., 'template', 'upgrade').
        dry_run: If True, skips execution and only logs actions.
        api: A comma-separated string of APIs to process,
             or None for all.
        extra_args: Extra arguments appending to the helm commands.

    Returns:
        True if validation succeeds, False otherwise.
    """
    selected_apis = config.keys()
    if api:
        apis = api.split(",")
        selected_apis = [api for api in selected_apis if api in apis]
    for selected_api in selected_apis:
        for t, v in RESOURCE_TYPES[selected_api].items():
            process_type(action, selected_api, t, v, config[selected_api], dry_run, [
                         {'name': selected_api}], extra_args)
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
        "--api",
        help="APIs to process, comma separated",
        type=str,
        default=None
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
            process(config=config, action=args.action,
                    dry_run=args.dry_run, api=args.api, extra_args=extra_args)
    else:
        call_global_action(
            action=args.action,
            dry_run=args.dry_run,
            extra_args=extra_args
        )


if __name__ == "__main__":
    sys.exit(main())
