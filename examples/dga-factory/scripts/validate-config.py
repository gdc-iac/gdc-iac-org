#!/usr/bin/env python3
import os
import subprocess
import pathlib
import logging
import argparse
import time

CONFIG_VARS = [
    'SCRIPTS_DIR', 'OUTPUT_DIR', 'USERS_YAML', 'GDCH_CHARTS_DIR',
    'HELM_CLI', 'ORG_NAME', 'IAC_PROJECT', 'IAC_SA', 'IAC_SA_FQN',
    'GDCH_ZONE', 'GDCH_DOMAIN', 'GDCH_CONSOLE', 'CLUSTER_NAME',
    'KUBECONFIG_PATH', 'GLOBAL_API_KUBECONFIG', 'ZONE_KUBECONFIG',
    'USER_CLUSTER_KUBECONFIG', 'SECRETS_DIR', 'NB_JUPYTER_IMAGE', 
    'S3_PROXY_IMAGE', 'CHARTS_DIR', 'S3_PROXY_ENABLED',
    'CLUSTER_K8S_VERSION', 'CLUSTER_POD_CIDR_SIZE', 'CLUSTER_SERVICE_CIDR_SIZE',
    'CLUSTER_INGRESS_SERVICE_IP_SIZE', 'CLUSTER_MACHINE_TYPE',
    'CLUSTER_NODE_COUNT', 'CLUSTER_NODE_POOL_NAME',
]


def setup_logging(verbose: bool = False) -> None:
    """Configures the logging settings."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Config")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    return parser.parse_known_args()


def run_helm(file_path, config, verbose):
    cmd = [
        config['HELM_CLI'],
        "template",
        str(file_path),
        f"--namespace={config['IAC_PROJECT']}",
        f"--charts-dir={config['GDCH_CHARTS_DIR']}",
        f"--sync-wait=0",
        f"--api=global,{config['GDCH_ZONE']},user:{config['CLUSTER_NAME']}",
        f"--api-kubeconfig={config['GLOBAL_API_KUBECONFIG']},"
        f"{config['ZONE_KUBECONFIG']},{config['USER_CLUSTER_KUBECONFIG']}"
    ]
    if verbose:
        cmd.append("-v")

    logging.info(f"Running: {' '.join(cmd)}")
    try:
        output = subprocess.check_output(cmd, text=True)
        with open(f"{file_path}.last-sync", 'w') as f:
            f.write(str(time.time()))
        if output and verbose:
            logging.debug(output)
    except subprocess.CalledProcessError as e:
        logging.error(
            f"Helm failed with return code {e.returncode} for {file_path}")
        logging.error(f"Error output: {e.output}")
        raise


def main():
    args, _ = parse_args()
    setup_logging(verbose=args.verbose)
    script_dir = pathlib.Path(__file__).resolve().parent
    config_path = script_dir / 'config.sh'

    # Source the config.sh script to populate the environment variables
    command = f"source {config_path} && env"
    proc = subprocess.run(['/bin/bash', '-c', command, str(
        pathlib.Path(__file__).resolve())], stdout=subprocess.PIPE, text=True)

    for line in proc.stdout.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

    config = {}
    for var in CONFIG_VARS:
        config[var] = os.environ.get(var)
    logging.debug(config)

    missing_vars = [var for var in CONFIG_VARS if not config.get(var)]
    if missing_vars:
        error_msg = (
            "Missing required environment variables from config.sh: "
            f"{', '.join(missing_vars)}"
        )
        raise RuntimeError(error_msg)

    output_dir_path = pathlib.Path(config['OUTPUT_DIR'])
    users_dir_path = output_dir_path / "users"
    shared_yaml_path = output_dir_path / "shared.yaml"
    run_helm(shared_yaml_path, config, args.verbose)

    for root, dirs, files in os.walk(users_dir_path):
        # Sort files so that -shared.yaml files are processed first
        files.sort(key=lambda f: (not f.endswith("-shared.yaml"), f))
        for file in files:
            if not file.endswith(".yaml"):
                continue

            file_path = pathlib.Path(root) / file

            if file.endswith("-shared.yaml"):
                # This is a shared config for the team. Run blindly.
                logging.info(f"Processing shared configuration: {file_path}")
                run_helm(file_path, config, args.verbose)
            else:
                # This is a specific user config.
                logging.info(f"Processing user configuration: {file_path}")
                run_helm(file_path, config, args.verbose)


if __name__ == "__main__":
    main()
