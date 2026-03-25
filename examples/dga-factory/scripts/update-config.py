#!/usr/bin/env python3
import os
import subprocess
import pathlib
import logging
import yaml
import jinja2
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
    parser = argparse.ArgumentParser(description="Sync Shared Configuration")
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

    output_dir_path = pathlib.Path(config['OUTPUT_DIR'])
    users_yaml_path = pathlib.Path(config['USERS_YAML'])

    with open(users_yaml_path, 'r') as f:
        users = yaml.safe_load(f)

    for team_name, team_data in users.items():
        team_users = team_data['users']
        team_admin = team_data['admin_user']
        # create team subdirectory in the users directory
        team_dir = output_dir_path / team_name
        team_dir.mkdir(parents=True, exist_ok=True)
        # create team shared yaml in the team directory
        team_shared_yaml_path = team_dir / f"{team_name}-shared.yaml"
        # render team shared yaml template from team-shared.yaml.j2
        template_path = script_dir.parent / "team-shared.yaml.j2"
        with open(template_path, 'r') as f:
            template = jinja2.Template(f.read())
        rendered_template = template.render(
            team_name=team_name,
            users=team_users,
            users_lowercase=[user.lower() for user in team_users],
            team_admin=team_admin,
            config=config
        )
        with open(team_shared_yaml_path, 'w') as f:
            logging.info(
                f"Rendered {template_path} to {team_shared_yaml_path}")
            f.write(rendered_template)
        for user in team_users:
            # render user template from user.yaml.j2
            user_yaml_path = team_dir / f"{user}.yaml"
            template_path = script_dir.parent / "user.yaml.j2"
            with open(template_path, 'r') as f:
                template = jinja2.Template(f.read())
            rendered_template = template.render(
                team_name=team_name,
                user=user,
                user_lowercase=user.lower(),
                team_admin=team_admin,
                config=config
            )
            with open(user_yaml_path, 'w') as f:
                logging.info(f"Rendered {template_path} to {user_yaml_path}")
                f.write(rendered_template)


if __name__ == "__main__":
    main()
