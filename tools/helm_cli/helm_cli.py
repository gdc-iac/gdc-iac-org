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
    --api global,us-central1-a \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

python3 tools/helm_cli/helm_cli.py upgrade \
    examples/multi-value-org/d4-shared.yaml \
    --api global,us-central1-a \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

D4 shared

python3 tools/helm_cli/helm_cli.py template \
    examples/multi-value-org/d4-shared.yaml \
    --api global,us-central1-a \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

python3 tools/helm_cli/helm_cli.py upgrade \
    examples/multi-value-org/d4-shared.yaml \
    --api global,us-central1-a \
    --api-kubeconfig global-api.kubeconfig,zone.kubeconfig -v

"""

import argparse
import hashlib
import logging
import subprocess
import sys
import tempfile
import os
from typing import List, Tuple, Union
import time

import yaml

RESOURCE_TREE = {}


def add_to_tree(path, obj=None):
    """Adds a path to the global RESOURCE_TREE and optionally parses an object to add children.

    Args:
        path: A list of strings representing the path to the node in the tree.
        obj: Optional object (list or dict) to inspect and add identified children nodes (like names, roles, account references, or subject names).
    """
    current = RESOURCE_TREE
    for node in path:
        if node not in current:
            current[node] = {}
        current = current[node]
        
    if obj is not None:
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    item_name = item.get('name') or item.get('role')
                    if item_name:
                        if item_name not in current:
                            current[item_name] = {}
                        subj_name = item.get('subject_name')
                        if subj_name:
                            current[item_name][subj_name] = {}
        elif isinstance(obj, dict):
            if 'account_ref' in obj:
                acc_ref = obj['account_ref']
                if acc_ref not in current:
                    current[acc_ref] = {}
            for k, v in obj.items():
                if isinstance(v, list):
                    if k not in current:
                        current[k] = {}
                    for item in v:
                        if isinstance(item, dict) and 'name' in item:
                            name = item['name']
                            if name not in current[k]:
                                current[k][name] = {}


def log_tree(tree, prefix=""):
    keys = list(tree.keys())
    for i, key in enumerate(keys):
        is_last = (i == len(keys) - 1)
        connector = "└── " if is_last else "├── "
        logging.info(f"{prefix}{connector}{key}")
        new_prefix = prefix + ("    " if is_last else "│   ")
        log_tree(tree[key], new_prefix)


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
            "backup-repositories": str,
            "backup-plans": str,
            "dashboards": list
        }
    },
    "user": {
        "user-cluster-workloads": list
    },
    "global": {
        "iam-roles": list,
        "billing": str,
        "billing-accounts": str,
        "projects": {
            "TYPE_SCOPE": "global",
            "IAC": list,
            "iam-roles": str,
            "project-service-accounts": str,
            "iam-role-bindings": list,
            "project-network-policies": list,
            "billing": str,
            "billing-bindings": str,
        }
    }
}


def setup_logging(verbose: bool = False, logfile: str = None, errorlogfile: str = None) -> None:
    """Configures the logging settings."""
    level = logging.DEBUG if verbose else logging.INFO
    
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.setLevel(level)
    
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    if logfile:
        file_handler = logging.FileHandler(logfile)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
    if errorlogfile:
        error_handler = logging.FileHandler(errorlogfile)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)


def action_cmd(
    action: str,
    kubeconfig: str = None,
    release_name: str = None,
    chart: str = None,
    chart_dir: str = None,
    output_dir: str = None,
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
        chart_dir: The directory containing the local helm charts (optional).
        output_dir: The directory where hydrated charts are saved (optional).
        values_file: The path to the values YAML file (optional).
        extra_args: Any extra arguments to append to the command (optional).

    Returns:
        A list of strings representing the literal helm subprocess command
        to execute.

    Raises:
        ValueError: If an explicitly mapped helm action string is not found.
    """
    if chart_dir:
        chart = f"{chart_dir}/{chart}"
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
        if output_dir is not None:
            cmd.extend(["--output-dir", output_dir])
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


def normalize_name(name: str) -> str:
    """
    Normalizes a resource name to be DNS-compliant and within Kubernetes limits.

    It replaces underscores with hyphens and converts to lowercase. If the
    resulting length exceeds 53 characters, truncates the name and appends a
    sha256 hash suffix to ensure uniqueness and compliance with length limits.

    Args:
        name: The original resource string name.

    Returns:
        A normalized and potentially truncated safe string identifier.
    """
    normalized_name = name.replace("_", "-").lower()
    if len(normalized_name) > 53:
        suffix = hashlib.sha256(name.encode()).hexdigest()[:8]
        normalized_name = normalized_name[:45] + "-" + suffix
    return normalized_name


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


def resource_action_exception_retriable(e):
    if e.output and "forbidden" in e.output:
        return True
    if e.output and "getting history for release" in e.output:
        return True
    return False
    

def call_resource_action(
    kubeconfig: str,
    action: str,
    dry_run: bool,
    parents: List[str],
    resource_name: str,
    resource_type: str,
    resource_config: dict,
    release_name: str,
    extra_args: List[str],
    charts_dir: str,
    output_dir: str,
    sync_wait: int,
    max_retries: int
) -> None:
    """
    Executes a helm action for a specific resource.

    It creates a temporary YAML values file for the resource config and
    invokes helm with the proper chart and release name.

    Args:
        kubeconfig: The path to the kubeconfig file.
        action: The helm action to perform.
        dry_run: If True, prints actions without executing them.
        parents: The parent context logic elements accumulation.
        resource_name: The logical identifier of the resource.
        resource_type: The type of the resource being processed.
        resource_config: The payload defining configuring fields.
        release_name: The corresponding helm target release identifier.
        extra_args: Extra arguments for the helm command.
        charts_dir: Directory housing base template configuration charts.
        output_dir: Path layout for outputting hydrated resource renders.
        sync_wait: Pre-configured sleep amount waiting for GDCH IAM propagation.
        max_retries: Maximum number of retries for failed executions.
    """
    if action == "hydrate":
        if output_dir is None:
            output_dir = f"./hydrated/"
        os.makedirs(f"{output_dir}/{resource_type}", exist_ok=True)
        if resource_name == "":
            resource_name = parents[-1].get('name')
        with open(f"{output_dir}/{resource_type}/{resource_name}.yaml", "w") as f:
            logging.info(f"Hydrating {resource_type}/{resource_name}.yaml")
            yaml.dump(resource_config, f)
    else:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as tmp:
            values_yaml = yaml.safe_dump(resource_config)
            logging.debug(values_yaml)
            tmp.write(values_yaml)
            tmp.flush()
            cmd = action_cmd(
                    kubeconfig=kubeconfig, action=action,
                    release_name=normalize_name(release_name),
                    chart=f"gdc-{resource_type}",
                    chart_dir=charts_dir,
                    output_dir=output_dir,
                    values_file=tmp.name, extra_args=extra_args
                )
            retry=0
            while retry < max_retries:
                try:
                    logging.info(f"{' '.join(cmd)}")
                    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
                    logging.info(f"Helm {action} {release_name} finished")
                    if output:
                        logging.info(output)
                    break
                except subprocess.CalledProcessError as e:
                    logging.debug(f"Helm {action} {release_name} failed with return code {e.returncode}")
                    logging.debug(f"Error output: {e.output}")
                    if resource_action_exception_retriable(e):
                        retry += 1
                        logging.info(f"Waiting to retry {action} {release_name} ({retry}/{max_retries})")
                        time.sleep(sync_wait)
                        continue
                    else:
                        raise e
                except FileNotFoundError as e:
                    logging.error(f"Error: Helm not found or could not be executed. {e}")
                    raise e
            
            if retry >= max_retries:
                raise TimeoutError(f"Helm {action} {release_name} timed out after {max_retries} retries")


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
    extra_args: List[str],
    charts_dir: str,
    output_dir: str,
    sync_wait: int,
    max_retries: int
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
        charts_dir: Directory pointing to the helm templates.
        output_dir: Target output location for 'hydrate' renders.
        sync_wait: Number of seconds to suspend execution post role binding.
        max_retries: Maximum number of retries for failed executions.
    """
    logging.debug(f"process_type {type_path}/{resource_type}")
    parent = parents[-1]
    parent_name = parent.get('name', type_path)
    parent_namespace = parent.get('namespace', parent_name)
    type_parts = type_path.split('/')
    parent_names = [p.get('name') for p in parents if p.get('name')]
    tree_path = []
    for i in range(len(type_parts)):
        tree_path.append(type_parts[i])
        if i < len(parent_names) and parent_names[i] != type_parts[i]:
            tree_path.append(parent_names[i])
    # IAC is a special case. It's not a resource type, but a config fragment
    if resource_type == "IAC":
        add_to_tree(tree_path + [resource_type])
        logging.debug(
            f"{action} iac {parent_name}/{resource_type}")
        release_name = f"{parent_name}-iac"
        resource_config = {
            'namespace': parent.get('name'),
            'iamrolebindings': iac_config
        }
        call_resource_action(
                kubeconfig=kubeconfig,
                action=action,
                dry_run=dry_run,
                parents=parents,
                resource_type="iac",
                resource_name=parent_name,
                resource_config=resource_config,
                release_name=release_name,
                extra_args=extra_args,
                charts_dir=charts_dir,
                output_dir=output_dir,
                sync_wait=sync_wait,
                max_retries=max_retries
            )
        return
    if resource_type not in config:
        return
    # generate one release per object list
    # in case of failure, exit function
    if type_tree is list:  
        logging.debug(
            f"{action} list {parent_name}/{resource_type}")
        obj = config[resource_type]
        release_name = f"{parent_name}-{resource_type}"
        resource_config = {
            'namespace': parent_namespace,
            resource_type.replace("-", ""): obj
        }
        if obj:
            add_to_tree(tree_path + [resource_type], obj)
        try:
            call_resource_action(
                kubeconfig=kubeconfig,
                action=action,
                dry_run=dry_run,
                parents=parents,
                resource_name=parent_name,
                resource_type=resource_type,
                resource_config=resource_config,
                release_name=release_name,
                extra_args=extra_args,
                charts_dir=charts_dir,
                output_dir=output_dir,
                sync_wait=sync_wait,
                max_retries=max_retries
            )
        except Exception as e:
            logging.error(f"Error creating {resource_type}: {e}")
            add_to_tree(tree_path + [resource_type, "(error)"])
            raise
        return
    # generate one release per object
    # in case of object failure, exit
    # in case of sub resource failure, continue
    if type_tree is str:  
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
            # exit on error in case of main object
            add_to_tree(tree_path + [resource_type], items)
            try:
                call_resource_action(
                    kubeconfig=kubeconfig,
                    action=action,
                    dry_run=dry_run,
                    parents=parents,
                    resource_name=obj_name,
                    resource_type=resource_type,
                    resource_config=resource_config,
                    release_name=release_name,
                    extra_args=extra_args,
                    charts_dir=charts_dir,
                    output_dir=output_dir,
                    sync_wait=sync_wait,
                    max_retries=max_retries
                )
            except Exception as e:
                logging.error(f"Error creating {resource_type}/{obj_name}: {e}")
                add_to_tree(tree_path + [resource_type, "(error)"])
                raise
            return

        for i, obj in enumerate(items):
            obj_name = obj.get('name', obj)
            add_to_tree(tree_path + [resource_type, obj_name])
            logging.debug(
                f"{action} object {parent_name}/{resource_type}/{obj_name}"
            )
            release_name = f"{parent_name}-{resource_type}-{obj_name}"
            resource_config = {resource_type.replace("-", ""): [{
                **obj,
                'namespace': parent_namespace,
                'location': obj.get('location', parents[0].get('name'))
            }]}
            # continue on error in case of sub resource
            try:
                call_resource_action(
                    kubeconfig=kubeconfig,
                    action=action,
                    dry_run=dry_run,
                    parents=parents,
                    resource_name=obj_name,
                    resource_type=resource_type,
                    resource_config=resource_config,
                    release_name=release_name,
                    extra_args=extra_args,
                    charts_dir=charts_dir,
                    output_dir=output_dir,
                    sync_wait=sync_wait,
                    max_retries=max_retries
                )
            except Exception as e:
                logging.error(f"Error creating {resource_type}/{obj_name}: {e}")
                add_to_tree(tree_path + [resource_type, obj_name, "(error)"])
        return
    # type_tree is a dict. Generate one release per object if TYPE_SCOPE
    # matches parent and recurse
    # continue loop but don't recurse on error
    for i, obj in enumerate(config[resource_type]):
        obj_name = obj.get('name', obj)
        add_to_tree(tree_path + [resource_type, obj_name])
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
            # exit on error in case of main object
            try:
                call_resource_action(
                    kubeconfig=kubeconfig,
                    action=action,
                    dry_run=dry_run,
                    parents=parents,
                    resource_name=obj_name,
                    resource_type=resource_type,
                    resource_config=resource_config,
                    release_name=release_name,
                    extra_args=extra_args,
                    charts_dir=charts_dir,
                    output_dir=output_dir,
                    sync_wait=sync_wait,
                    max_retries=max_retries,
                )
            except Exception as e:
                logging.error(f"Error creating {resource_type}/{obj_name}: {e}")
                add_to_tree(tree_path + [resource_type, obj_name, "(error)"])
                raise
        for t, v in type_tree.items():
            new_parents = parents + [obj]
            # continue loop in case of error
            try:
                process_type(
                    action=action, type_path=f"{type_path}/{resource_type}",
                    resource_type=t, type_tree=v,
                    config=config[resource_type][i],
                    iac_config=iac_config, kubeconfig=kubeconfig,
                    dry_run=dry_run, parents=new_parents, extra_args=extra_args,
                    charts_dir=charts_dir,
                    output_dir=output_dir,
                    sync_wait=sync_wait,
                    max_retries=max_retries,
                )
            except TimeoutError as e:
                logging.error(f"Error processing {t}/{v}: {e}")
                pass


def process_user_workload(
    action: str, cluster_name: str, config: dict, iac_config: dict,
    kubeconfig: str, dry_run: bool, extra_args: List[str],
    output_dir: str,
    max_retries: int,
    sync_wait: int = 15
) -> bool:
    """
    Process user workload configuration and iterate over nested custom charts.

    Allows execution of arbitrary helm charts within a specific user cluster
    namespace without coupling them strictly to standard factory-provided charts.

    Args:
        action: The action to perform on each user workload chart.
        cluster_name: The target physical user cluster identifier.
        config: Specific workload configuration slice.
        iac_config: IaC specific binding configurations.
        kubeconfig: Path to the correct user cluster kubeconfig.
        dry_run: If True, log intended actions without executing side-effects.
        extra_args: Additional arbitrary arguments for commands.
        output_dir: Target output location for 'hydrate' render generation.
        max_retries: Maximum number of retries for failed executions.
    """
    logging.debug(f"process_user_workload action: {action}, "
    f"cluster_name: {cluster_name}, config: {config}, "
    f"iac_config: {iac_config}, kubeconfig: {kubeconfig}, "
    f"dry_run: {dry_run}, extra_args: {extra_args}, "
    f"output_dir: {output_dir}, "
    f"max_retries: {max_retries}"
    )
    for chart in config.get("charts", []):
        add_to_tree([cluster_name, chart['release_name']])
        logging.info(f"Processing chart: {chart}")
        if action == "hydrate":
            current_output_dir = output_dir if output_dir else "./hydrated"
            current_output_dir = current_output_dir.rstrip('/')
            # chart name can be path
            chart_name = chart['name'].split('/')[-1]
            chart_output_dir = os.path.join(current_output_dir, cluster_name, chart_name)
            os.makedirs(chart_output_dir, exist_ok=True)
            with open(os.path.join(chart_output_dir, f"{chart['release_name']}.yaml"), "w") as f:
                logging.info(f"Hydrating {cluster_name}/{chart_name}/{chart['release_name']}.yaml")
                yaml.dump(chart['values'], f)
        else:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as tmp:
                values_yaml = yaml.safe_dump(chart['values'])
                logging.debug(values_yaml)
                tmp.write(values_yaml)
                tmp.flush()
                cmd = action_cmd(
                    kubeconfig=kubeconfig, action=action,
                    release_name=chart['release_name'],
                    chart=chart['name'],
                    output_dir=output_dir,
                    values_file=tmp.name, extra_args=extra_args
                )
                retry=0
                while retry < max_retries:
                    try:
                        logging.info(f"{' '.join(cmd)}")
                        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
                        logging.info(f"Helm {action} {chart['release_name']} finished")
                        if output:
                            logging.info(output)
                        break
                    except subprocess.CalledProcessError as e:
                        logging.error(f"Helm failed with return code {e.returncode}")
                        logging.error(f"Error output (if captured): {e.output}")
                        if resource_action_exception_retriable(e):
                            retry += 1
                            logging.info(f"Waiting to retry {action} {chart['release_name']} ({retry}/{max_retries})")
                            time.sleep(sync_wait)
                            continue
                        else:
                            raise e
                    except FileNotFoundError as e:
                        logging.error(f"Error: Helm not found or could not be executed. {e}")
                        raise e
                
                if retry >= max_retries:
                    raise TimeoutError(f"Helm {action} {chart['release_name']} timed out after {max_retries} retries")
            
            
    

def process(
    config: dict, action: str, dry_run: bool, api: str,
    charts_dir: str,
    output_dir: str,
    api_kubeconfig: str, extra_args: List[str],
    sync_wait: int,
    max_retries: int
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
        charts_dir: Directory containing generic helm charts.
        output_dir: Directory for generated template outputs if 'hydrate' is passed.
        api_kubeconfig: A comma-separated string of kubeconfig files
                        corresponding to the APIs.
        extra_args: Extra arguments appending to the helm commands.
        sync_wait: Pre-configured integer for waiting between cluster propagations.
        max_retries: Maximum number of retries for failed executions.

    Returns:
        True if validation succeeds, False otherwise.
    """
    api_kubeconfigs = []
    iac_config = config["iac"]
    if api:
        selected_apis = api.split(",")
    if api_kubeconfig:
        api_kubeconfigs = api_kubeconfig.split(",")
        if len(api_kubeconfigs) != len(selected_apis):
            raise ValueError(
                f"Number of api_kubeconfigs must match number of apis:\n"
                f"apis={selected_apis}\n"
                f"api_kubeconfigs={api_kubeconfigs}"
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

        if selected_api not in config:
            logging.debug(f"API {selected_api} not found in config")
            continue
        if api_type in ["global", "zone"]:
            for t, v in api_schema.items():
                process_type(
                    action=action, type_path=selected_api, resource_type=t,
                    type_tree=v, config=config[selected_api],
                    iac_config=iac_config, kubeconfig=kubeconfig,
                dry_run=dry_run, parents=[
                    {'name': actual_name, 'namespace': namespace}],
                extra_args=extra_args,
                charts_dir=charts_dir,
                output_dir=output_dir,
                sync_wait=sync_wait,
                max_retries=max_retries
            ) 
        else:
            process_user_workload(
                action=action, cluster_name=actual_name,
                config=config[selected_api],
                iac_config=iac_config, kubeconfig=kubeconfig,
                dry_run=dry_run, 
                extra_args=extra_args,
                output_dir=output_dir,
                max_retries=max_retries,
                sync_wait=sync_wait
            )
    logging.info("Resource Tree:")
    log_tree(RESOURCE_TREE)
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
        "--charts-dir",
        help="Directory containing the helm charts",
        type=str,
        default="../../charts"
    )

    parser.add_argument(
        "--output-dir",
        help="Directory to output the hydrated charts to",
        type=str,
        default=None
    )

    parser.add_argument(
        "--sync-wait",
        help="Wait for resources to be ready after sync (in seconds)",
        type=int,
        default=15
    )

    parser.add_argument(
        "--max-retries",
        help="Maximum number of retries for failed syncs",
        type=int,
        default=3
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

    parser.add_argument(
        "--logfile",
        help="Path to log file for all output",
        type=str,
        default=None
    )

    parser.add_argument(
        "--errorlogfile",
        help="Path to log file for error output only",
        type=str,
        default=None
    )

    return parser.parse_known_args(args)


def main() -> int:
    """
    Main entry point for executing helm_cli.py.
    Initializes standard stdout formatting layout and delegates directly to
    core process execution flow logic.
    """
    args, extra_args = parse_args(sys.argv[1:])
    setup_logging(args.verbose, args.logfile, args.errorlogfile)
    if args.config:
        with open(args.config, "r") as f:
            logging.info(f"Processing file {args.config}")
            config = yaml.safe_load(f)
            process(
                config=config, action=args.action,
                dry_run=args.dry_run, api=args.api,
                charts_dir=args.charts_dir,
                output_dir=args.output_dir,
                api_kubeconfig=args.api_kubeconfig, extra_args=extra_args,
                sync_wait=args.sync_wait,
                max_retries=args.max_retries
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