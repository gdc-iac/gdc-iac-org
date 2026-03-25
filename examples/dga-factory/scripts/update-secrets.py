#!/usr/bin/env python3
import os
import subprocess
import pathlib
import logging
import yaml
import jinja2
import base64
import argparse

CONFIG_VARS = [
    'SCRIPTS_DIR', 'OUTPUT_DIR', 'USERS_YAML', 'GDCH_CHARTS_DIR',
    'HELM_CLI', 'ORG_NAME', 'IAC_PROJECT', 'IAC_SA', 'IAC_SA_FQN',
    'GDCH_ZONE', 'GDCH_DOMAIN', 'GDCH_CONSOLE', 'CLUSTER_NAME',
    'KUBECONFIG_PATH', 'GLOBAL_API_KUBECONFIG', 'ZONE_KUBECONFIG',
    'USER_CLUSTER_KUBECONFIG', 'SECRETS_DIR', 'NB_JUPYTER_IMAGE',
    'S3_PROXY_IMAGE'
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
    parser = argparse.ArgumentParser(
        description="Update Secrets Configuration")
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

    project_dir_path = pathlib.Path(config['SCRIPTS_DIR']).parent
    users_yaml_path = pathlib.Path(config['USERS_YAML'])

    with open(users_yaml_path, 'r') as f:
        users = yaml.safe_load(f)

    for team_name, team_data in users.items():
        team_users = team_data['users']
        # create team subdirectory in the secrets directory
        team_dir = project_dir_path / 'secrets' / team_name
        team_dir.mkdir(parents=True, exist_ok=True)

        for user in team_users:
            secret_yaml_path = team_dir / f"{user}-secret.yaml"
            endpoint_cmd = [
                "kubectl", f"--kubeconfig={config['ZONE_KUBECONFIG']}",
                "--namespace", f"{team_name}-shared-infra",
                "get", "buckets", f"{team_name}-s3-rw1",
                "-o", "jsonpath={.status.endpoint}"
            ]
            logging.debug(' '.join(endpoint_cmd))
            try:
                endpoint = subprocess.check_output(
                    endpoint_cmd, text=True).strip()
            except subprocess.CalledProcessError:
                endpoint = ""

            subject_key = 'object\\.gdc\\.goog/subject'
            annotations_filter = (
                f"?(@.metadata.annotations['{subject_key}']=='{user}')"
            )
            jsonpath_cmd = (
                f"jsonpath={{.items[{annotations_filter}].metadata.name}}"
            )
            secret_name_cmd = [
                "kubectl", f"--kubeconfig={config['ZONE_KUBECONFIG']}",
                "get", "secrets", "-n", "object-storage-access-keys",
                "-o", jsonpath_cmd
            ]
            logging.debug(' '.join(secret_name_cmd))
            secret_name = subprocess.check_output(
                secret_name_cmd, text=True).strip()

            if secret_name:
                access_key_cmd = [
                    "kubectl", f"--kubeconfig={config['ZONE_KUBECONFIG']}",
                    "get", "-n", "object-storage-access-keys",
                    f"secret/{secret_name}",
                    "-o", "jsonpath={.data.access-key-id}"
                ]
                logging.debug(' '.join(access_key_cmd))
                aws_access_key_id_b64 = subprocess.check_output(
                    access_key_cmd, text=True).strip()
                aws_access_key_id = base64.b64decode(
                    aws_access_key_id_b64).decode('utf-8')

                secret_key_cmd = [
                    "kubectl", f"--kubeconfig={config['ZONE_KUBECONFIG']}",
                    "get", "-n", "object-storage-access-keys",
                    f"secret/{secret_name}",
                    "-o", "jsonpath={.data.secret-access-key}"
                ]
                logging.debug(' '.join(secret_key_cmd))
                aws_secret_access_key_b64 = subprocess.check_output(
                    secret_key_cmd, text=True).strip()
                aws_secret_access_key = base64.b64decode(
                    aws_secret_access_key_b64).decode('utf-8')

                secret_template_path = project_dir_path / 'secret.yaml.j2'
                with open(secret_template_path, 'r') as tf:
                    s_template = jinja2.Template(tf.read())
                with open(secret_yaml_path, 'w') as of:
                    of.write(s_template.render(
                        endpoint=endpoint,
                        aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key,
                        config=config,
                    ))
                logging.info(
                    f"Rendered {secret_template_path} to {secret_yaml_path}")
            else:
                logging.warning(
                    f"No secret found for user {user} in team {team_name}")


if __name__ == "__main__":
    main()
