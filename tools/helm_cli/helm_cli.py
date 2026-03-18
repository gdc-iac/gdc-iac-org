#!/usr/bin/env python3
"""
helm_cli.py - GDCH Configured Helm execution wrapper

This script is designed to parse GDCH (Google Distributed Cloud Hosted)
specific YAML configuration objects (like 'global', 'projects', 'iac')
and iterate through nested lists to dispatch contextual variables into
local GDCH helm charts (such as 'gdc-iac', 'gdc-iam-role-bindings',
'gdc-project-network-policies').

Usage Examples:

D2 user

python3 tools/helm_cli/helm_cli.py template \
    examples/multi-value-org/d4-shared.yaml \
    --api global,lux-central1-b \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

python3 tools/helm_cli/helm_cli.py upgrade \
    examples/multi-value-org/d4-shared.yaml \
    --api global,lux-central1-b \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

D4 shared

python3 tools/helm_cli/helm_cli.py template \
    examples/multi-value-org/d4-shared.yaml \
    --api global,lux-central1-b \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

python3 tools/helm_cli/helm_cli.py upgrade \
    examples/multi-value-org/d4-shared.yaml \
    --api global,lux-central1-b \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

"""

import argparse
import logging
import subprocess
import sys
import tempfile
from typing import List, Tuple, Union

import yaml

RESOURCE_SCHEMA = {
    # str: each resource instance is a separate release
    # list: all resource instances are a single release
    "zone": {
        "clusters": str,
        "projects": {
            "TYPE_SCOPE": "global",
            "rbac-role-bindings": list,
            "buckets": str,
            "notebooks": str,
            "harbors": str,
            "backup-repositories": str
        }
    },
    "user": {
        "user-cluster-workloads": list
    },
    "global": {
        "iam-roles": str,
        "billing": str,
        "projects": {
            "TYPE_SCOPE": "global",
            "IAC": list,
            "iam-roles": str,
            "project-service-accounts": str,
            "iam-role-bindings": list,
            "project-network-policies": list,
            "billing": str,
        }
    }
}


def setup_logging(verbose: bool = False) -> None:
    """Configures the logging settings."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
        A list of strings representing the literal helm subprocess command
        to execute.

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
    action: str,
    resource_type: str,
    resource_config: dict,
    release_name: str,
    extra_args: List[str]
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
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as tmp:
            values_yaml = yaml.safe_dump(resource_config)
            logging.debug(values_yaml)
            tmp.write(values_yaml)
            tmp.flush()
            cmd = action_cmd(
                kubeconfig=kubeconfig, action=action,
                release_name=release_name,
                chart=f"../../charts/gdc-{resource_type}",
                values_file=tmp.name, extra_args=extra_args
            )
            logging.info(f"{' '.join(cmd)}")
            output = subprocess.check_output(cmd, text=True)
            logging.info(f"Helm {action} {release_name} finished")
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
    parent_name = parent.get('name', type_path)
    parent_namespace = parent.get('namespace', parent_name)
    # IAC is a special case. It's not a resource type, but a config fragment
    if resource_type == "IAC":
        logging.debug(
            f"{action} iac {parent_name}/{resource_type}")
        release_name = f"{parent_name}-iac"
        resource_config = {
            'namespace': parent.get('name'),
            'iamrolebindings': iac_config
        }
        if not dry_run:
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action,
                resource_type="iac",
                resource_config=resource_config,
                release_name=release_name,
                extra_args=extra_args
            )
        return
    if resource_type not in config:
        return
    if type_tree is list:  # generate one release per object list
        logging.debug(
            f"{action} list {parent_name}/{resource_type}")
        obj = config[resource_type]
        release_name = f"{parent_name}-{resource_type}"
        resource_config = {
            'namespace': parent_namespace,
            resource_type.replace("-", ""): obj
        }
        if not dry_run:
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action,
                resource_type=resource_type,
                resource_config=resource_config,
                release_name=release_name,
                extra_args=extra_args
            )
        return
    if type_tree is str:  # generate one release per object
        items = config[resource_type]
        if isinstance(items, dict):
            obj_name = items.get('name', '')
            release_name = f"{parent_name}-{resource_type}-{obj_name}" if obj_name else f"{parent_name}-{resource_type}"
            logging.debug(
                f"{action} object {parent_name}/{resource_type}/{obj_name}"
            )
            resource_config = {resource_type.replace("-", ""): {
                **items,
                'namespace': parent_namespace,
                'location': items.get('location', parents[0].get('name'))
            }}
            if not dry_run:
                call_resource_action(
                    kubeconfig=kubeconfig,
                    action=action,
                    resource_type=resource_type,
                    resource_config=resource_config,
                    release_name=release_name,
                    extra_args=extra_args
                )
            return

        for i, obj in enumerate(items):
            obj_name = obj.get('name', obj)
            logging.debug(
                f"{action} object {parent_name}/{resource_type}/{obj_name}"
            )
            release_name = f"{parent_name}-{resource_type}-{obj_name}"
            resource_config = {resource_type.replace("-", ""): [{
                **obj,
                'namespace': parent_namespace,
                'location': obj.get('location', parents[0].get('name'))
            }]}
            if not dry_run:
                call_resource_action(
                    kubeconfig=kubeconfig,
                    action=action,
                    resource_type=resource_type,
                    resource_config=resource_config,
                    release_name=release_name,
                    extra_args=extra_args
                )
        return
    # type_tree is a dict. Generate one release per object if TYPE_SCOPE
    # matches parent and recurse
    for i, obj in enumerate(config[resource_type]):
        obj_name = obj.get('name', obj)
        logging.debug(
            f"{action} object {parent_name}/{resource_type}/{obj_name}"
        )
        resource_scope = type_tree.get(
            "TYPE_SCOPE", parent.get("name", type_path))
        skip_helm = dry_run
        if resource_scope != parent.get("name", type_path):
            skip_helm = True
        release_name = f"{parent_name}-{resource_type}-{obj_name}"
        resource_config = {resource_type.replace("-", ""): [{
            **obj,
            'namespace': parent_namespace
        }]}
        if not skip_helm:
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action,
                resource_type=resource_type,
                resource_config=resource_config,
                release_name=release_name,
                extra_args=extra_args
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
    Entry point for traversing the extracted Python dictionary generated by
    PyYAML loading the custom YAML config, iteratively generating targeted
    Helm executions against specific Kubernetes GDCH API scopes based on
    RESOURCE_SCHEMA definitions.

    Args:
        config: The complete configuration dictionary loaded from YAML.
        action: The string helm action to perform (e.g., 'template').
        dry_run: If True, skips subprocess execution and only logs
            generated strings.
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

        if selected_api == "global":
            api_type = "global"
            actual_name = "global"
            namespace = "platform"
        elif ":" in selected_api:
            api_type, actual_name = selected_api.split(":", 1)
            namespace = actual_name
        else:
            api_type = "zone"
            actual_name = selected_api
            namespace = actual_name
        api_schema = RESOURCE_SCHEMA.get(api_type, RESOURCE_SCHEMA["zone"])

        for t, v in api_schema.items():
            process_type(
                action=action, type_path=selected_api, resource_type=t,
                type_tree=v, config=config[selected_api],
                iac_config=iac_config, kubeconfig=kubeconfig,
                dry_run=dry_run, parents=[
                    {'name': actual_name, 'namespace': namespace}],
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
