#!/usr/bin/env python3
import os
import subprocess
import pathlib
import logging
import argparse

CONFIG_VARS = [
    'SCRIPTS_DIR', 'OUTPUT_DIR', 'USERS_YAML', 'GDCH_CHARTS_DIR',
    'HELM_CLI', 'ORG_NAME', 'IAC_PROJECT', 'IAC_SA', 'IAC_SA_FQN',
    'GDCH_ZONE', 'GDCH_DOMAIN', 'GDCH_CONSOLE', 'CLUSTER_NAME',
    'KUBECONFIG_PATH', 'GLOBAL_API_KUBECONFIG', 'ZONE_KUBECONFIG',
    'USER_CLUSTER_KUBECONFIG', 'SECRETS_DIR'
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
    parser = argparse.ArgumentParser(description="Sync Secrets")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    return parser.parse_known_args()

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

    secrets_dir_path = pathlib.Path(config['SECRETS_DIR'])

    for root, dirs, files in os.walk(secrets_dir_path):
        for file in files:
            if not file.endswith("-secret.yaml"):
                continue

            file_path = pathlib.Path(root) / file
            user = file.replace("-secret.yaml", "")
            user_lowercase = user.lower()

            secret_name = f"{user_lowercase}-s3-proxy-config"
            namespace = user_lowercase

            logging.info(f"Creating secret {secret_name} in namespace {namespace} from {file_path}")
            
            # Use kubectl create secret generic + apply to handle updates
            cmd = [
                "kubectl", f"--kubeconfig={config['USER_CLUSTER_KUBECONFIG']}",
                "create", "secret", "generic", secret_name,
                f"--from-file=config.yaml={file_path}",
                "-n", namespace,
                "--dry-run=client", "-o", "yaml"
            ]
            
            try:
                # Generate manifest
                manifest = subprocess.check_output(cmd, text=True)
                
                # Apply manifest
                apply_cmd = [
                    "kubectl", f"--kubeconfig={config['USER_CLUSTER_KUBECONFIG']}",
                    "apply", "--validate=false", "-f", "-"
                ]
                subprocess.run(apply_cmd, input=manifest, text=True, check=True)
                logging.info(f"Successfully applied secret {secret_name}")
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to create secret {secret_name}: {e}")
                raise

if __name__ == "__main__":
    main()
