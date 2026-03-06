#!/usr/bin/env python3
"""
helm_cli.py - GDCH Configured Helm execution wrapper

This script is designed to parse GDCH (Google Distributed Cloud Hosted) specific YAML
configuration objects (like 'global', 'projects', 'iac') and iterate through nested lists 
to dispatch contextual variables into local GDCH helm charts (such as 'gdc-iac', 
'gdc-iam-role-bindings', 'gdc-project-network-policies').

Usage Examples:
python3 helm_cli.py /mnt/c/temp/DGA/Repo/examples/multi-value-org/d2-user.yaml --dry-run -v
python3 helm_cli.py /mnt/c/temp/DGA/Repo/examples/multi-value-org/d4-shared.yaml --dry-run -v

python3 /mnt/c/temp/DGA/Repo/tools/helm_cli/helm_cli.py /mnt/c/temp/DGA/Repo/examples/multi-value-org/d2-user.yaml -a install -a upgrade -v
python3 /mnt/c/temp/DGA/Repo/tools/helm_cli/helm_cli.py /mnt/c/temp/DGA/Repo/examples/multi-value-org/d4-shared.yaml -a install -a upgrade -v
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
        "notebooks": str
    }
},
    {
        "global": {
            "iam-roles": str,
            "projects": {
                "TYPE_SCOPE": "global",
                "IAC": list,
                "iam-roles": str,
                "iam-role-bindings": list,
                "project-network-policies": list
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
    Constructs the target values.yaml configuration dictionary corresponding 
    to the specific GDCH Helm Chart requirements.

    Args:
        resource_type: The type of the resource (e.g., 'buckets', 'project-network-policies').
        obj: The resource properties dictionary.
        parents: A list of parent objects providing context (e.g. namespaces).

    Returns:
        A dictionary representing the transformed config for the resource.
    """
    parent = parents[-1]
    if resource_type == "iac":
        return {
            'namespace': parent.get('name'),
            'iamrolebindings': obj
        }
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
    if resource_type == "project-network-policies":
        return {
            'namespace': parent.get('name'),
            'projectnetworkpolicies': obj
        }
    if resource_type == "notebooks":
        return {"notebooks": [{
            **obj,
            'namespace': parent.get('name')
        }]}
    return {resource_type.replace("-", ""): [obj]}


def release_name(
    resource_type: str, obj: Union[dict, list], parents: List[dict]
) -> str:
    """
    Generates a standardized predictable Helm release name for a resource instance.

    Args:
        resource_type: The type of the resource (e.g., 'project-network-policies').
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
    kubeconfig: str = None,
    release_name: str = None,
    chart: str = None,
    values_file: str = None,
    extra_args: List[str] = None
) -> List[str]:
    """
    Constructs the corresponding helm command line for a given action.

    Args:
        action: The helm action to perform (e.g., 'upgrade', 'template').
        kubeconfig: The path to the kubeconfig file (optional).
        release_name: The name of the helm release (optional).
        chart: The path to the local helm chart (optional).
        values_file: The path to the values YAML file (optional).
        extra_args: Any extra arguments to append to the command (optional).

    Returns:
        A list of strings representing the literal helm subprocess command to execute.

    Raises:
        ValueError: If an explicitly mapped helm action string is not found.
    """
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        cmd = ["helm", "--debug"]
    else:
        cmd = ["helm"]
    if kubeconfig:
        cmd.extend(["--kubeconfig", kubeconfig])
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
    action: str, dry_run: bool, kubeconfig: str, extra_args: List[str]
) -> None:
    """
    Executes a global helm action (e.g., 'list') that does not require a chart.

    Args:
        action: The helm action to perform.
        dry_run: If True, skips actual execution and only logs.
        kubeconfig: The path to the kubeconfig file.
        extra_args: Extra arguments to append to the command.
    """
    cmd = action_cmd(
        kubeconfig=kubeconfig, action=action, extra_args=extra_args
    )
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
    kubeconfig: str,
    action: str, resource_type: str, obj: Union[dict, list],
    parents: List[dict], extra_args: List[str]
) -> None:
    """
    Executes a helm action for a specific resource.

    It creates a temporary YAML values file for the resource config and
    invokes helm with the proper chart and release name.

    Args:
        kubeconfig: The path to the kubeconfig file.
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
                kubeconfig=kubeconfig, action=action, release_name=release,
                chart=f"../../charts/gdc-{resource_type}",
                values_file=tmp.name, extra_args=extra_args
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
    iac_config: dict,
    kubeconfig: str,
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
        iac_config: The iac configuration fragment.
        kubeconfig: The kubeconfig to use for this action.
        dry_run: If True, prints actions without executing them.
        parents: A list of parent nodes accumulating context.
        extra_args: Extra arguments to pass down to helm executions.
    """
    logging.debug(f"process_type {type_path}/{resource_type}")
    parent = parents[-1]
    if resource_type == "IAC":
        logging.debug(
            f"{action} iac {parent.get('name', type_path)}/{resource_type}")
        if not dry_run:
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action, resource_type="iac",
                obj=iac_config, parents=parents, extra_args=extra_args
            )
        return
    if resource_type not in config:
        return
    if type_tree is list:  # generate one release per object list
        logging.debug(
            f"{action} list {parent.get('name', type_path)}/{resource_type}")
        obj = config[resource_type]
        if not dry_run:
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action, resource_type=resource_type,
                obj=obj, parents=parents, extra_args=extra_args
            )
        return
    if type_tree is str:  # generate one release per object
        for i, obj in enumerate(config[resource_type]):
            parent_name = parent.get('name', type_path)
            obj_name = obj.get('name', obj)
            logging.debug(
                f"{action} object {parent_name}/{resource_type}/{obj_name}"
            )
            if not dry_run:
                call_resource_action(
                    kubeconfig=kubeconfig,
                    action=action, resource_type=resource_type,
                    obj=obj, parents=parents, extra_args=extra_args
                )
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
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action, resource_type=resource_type,
                obj=obj, parents=parents, extra_args=extra_args
            )
        for t, v in type_tree.items():
            parents.append(obj)
            process_type(
                action=action, type_path=f"{type_path}/{resource_type}",
                resource_type=t, type_tree=v,
                config=config[resource_type][i],
                iac_config=iac_config, kubeconfig=kubeconfig,
                dry_run=dry_run, parents=parents, extra_args=extra_args
            )


def process(
    config: dict, action: str, dry_run: bool, api: str,
    api_kubeconfig: str, extra_args: List[str]
) -> bool:
    """
    Entry point for traversing the extracted Python dictionary generated by PyYAML 
    loading the custom YAML config, iteratively generating targeted Helm executions 
    against specific Kubernetes GDCH API scopes based on RESOURCE_TYPES definitions.

    Args:
        config: The complete configuration dictionary loaded from YAML.
        action: The string helm action to perform (e.g., 'template', 'upgrade').
        dry_run: If True, skips subprocess execution and only logs generated strings.
        api: A comma-separated string of APIs to process,
             or None for all.
        api_kubeconfig: A comma-separated string of kubeconfig files
                        corresponding to the APIs.
        extra_args: Extra arguments appending to the helm commands.

    Returns:
        True if validation succeeds, False otherwise.
    """
    selected_apis = [api for api in config.keys() if api not in ["iac"]]
    api_kubeconfigs = []
    iac_config = config["iac"]
    if api:
        apis = api.split(",")
        selected_apis = [api for api in selected_apis if api in apis]
    if api_kubeconfig:
        api_kubeconfigs = api_kubeconfig.split(",")
        if len(api_kubeconfigs) != len(selected_apis):
            raise ValueError(
                "Number of api_kubeconfigs must match number of apis"
            )
    for i, selected_api in enumerate(selected_apis):
        kubeconfig = api_kubeconfigs[i] if api_kubeconfig else None
        for t, v in RESOURCE_TYPES[selected_api].items():
            process_type(
                action=action, type_path=selected_api, resource_type=t,
                type_tree=v, config=config[selected_api],
                iac_config=iac_config, kubeconfig=kubeconfig,
                dry_run=dry_run, parents=[{'name': selected_api}],
                extra_args=extra_args
            )
    return True


def parse_args(args: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="GDCH Helm CLI Wrapper")

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
        "--api-kubeconfig",
        help="Kubeconfigs to use for API calls, comma separated",
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
    """
    Main entry point for executing helm_cli.py.
    Initializes standard stdout formatting layout and delegates directly to 
    core process execution flow logic.
    """
    args, extra_args = parse_args(sys.argv[1:])
    setup_logging(args.verbose)
    if args.config:
        with open(args.config, "r") as f:
            logging.info(f"Processing file {args.config}")
            config = yaml.safe_load(f)
            process(
                config=config, action=args.action,
                dry_run=args.dry_run, api=args.api,
                api_kubeconfig=args.api_kubeconfig, extra_args=extra_args
            )
    else:
        call_global_action(
            kubeconfig=args.api_kubeconfig,
            action=args.action,
            dry_run=args.dry_run,
            extra_args=extra_args
        )


if __name__ == "__main__":
    sys.exit(main())
