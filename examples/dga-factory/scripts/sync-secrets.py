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
    'USER_CLUSTER_KUBECONFIG', 'SECRETS_DIR', 'CHARTS_DIR', 'S3_PROXY_ENABLED'
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
            logging.debug(f"Processing file {file}")
            file_path = pathlib.Path(root) / file
            project = file.replace("-secret.yaml", "")

            secret_name = f"s3-proxy-config"
            namespace = project

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

                # Deploy dga-secret-sync
                helm_cmd = [
                    "helm", "upgrade", "--install",
                    f"{namespace}-secret-sync",
                    str(pathlib.Path(config['CHARTS_DIR']) / "dga-secret-sync"),
                    f"--namespace={config['IAC_PROJECT']}",
                    f"--kubeconfig={config['USER_CLUSTER_KUBECONFIG']}",
                    f"--set", f"namespace={namespace}",
                    f"--set", f"notebook_name=nb",
                    f"--set", f"s3_proxy_config_pvc=s3-proxy-config",
                    f"--set", f"secret_name={secret_name}",
                    "--debug"
                ]
                
                logging.info(f"Running: {' '.join(helm_cmd)}")
                try:
                    result = subprocess.run(helm_cmd, text=True, capture_output=True)
                    if result.stdout:
                        logging.info("Helm output:")
                        logging.info(result.stdout)
                    result.check_returncode()
                    logging.info(f"Successfully deployed dga-secret-sync for {namespace}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to deploy dga-secret-sync for {namespace}: {e}")
                    if e.stdout:
                        logging.info("Helm output (error):")
                        logging.info(e.stdout)
                    if e.stderr:
                        logging.warning("Helm error output (error):")
                        logging.warning(e.stderr)
                    raise
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to process secret {secret_name}: {e}")
                raise

if __name__ == "__main__":
    main()
