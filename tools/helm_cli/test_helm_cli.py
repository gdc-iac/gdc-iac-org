import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add the directory containing helm_cli.py to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import helm_cli  # noqa: E402


class TestHelmCli(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None

    def test_resource_config_buckets(self):
        resource_type = "buckets"
        obj = {"name": "my-bucket", "location": "us-west1"}
        parents = [{"name": "my-project"}]
        _ = (resource_type, obj, parents)

    def test_action_cmd_upgrade(self):
        action = "upgrade"
        release = "my-release"
        chart = "my-chart"
        values = "values.yaml"
        extra = ["--wait", "--timeout", "10m"]

        expected = [
            "helm", "upgrade", "--install", release, chart, "-f", values,
            "--wait", "--timeout", "10m"
        ]
        result = helm_cli.action_cmd(
            action, release_name=release, chart=chart, values_file=values,
            extra_args=extra
        )
        self.assertEqual(result, expected)

    def test_action_cmd_list(self):
        action = "list"
        extra = ["-A"]
        expected = ["helm", "list", "-A"]
        result = helm_cli.action_cmd(action, extra_args=extra)
        self.assertEqual(result, expected)

    def test_action_cmd_kubeconfig(self):
        action = "list"
        kubeconfig = "/path/to/kubeconfig"
        extra = ["-A"]
        expected = [
            "helm", "--kubeconfig", "/path/to/kubeconfig", "list", "-A"
        ]
        result = helm_cli.action_cmd(
            action=action, kubeconfig=kubeconfig, extra_args=extra
        )
        self.assertEqual(result, expected)

    def test_action_cmd_other_actions(self):
        self.assertEqual(
            helm_cli.action_cmd(
                "install", release_name="r", chart="c",
                values_file="v", extra_args=[]
            ),
            ["helm", "install", "r", "c", "-f", "v"]
        )
        self.assertEqual(
            helm_cli.action_cmd(
                "lint", chart="c", values_file="v", extra_args=[]
            ),
            ["helm", "lint", "c", "-f", "v"]
        )
        self.assertEqual(
            helm_cli.action_cmd("show", chart="c", extra_args=[]),
            ["helm", "show", "all", "c"]
        )
        self.assertEqual(
            helm_cli.action_cmd(
                "uninstall", release_name="r", extra_args=[]
            ),
            ["helm", "uninstall", "r"]
        )
        self.assertEqual(
            helm_cli.action_cmd("status", release_name="r", extra_args=[]),
            ["helm", "status", "r"]
        )
        self.assertEqual(
            helm_cli.action_cmd("get all", release_name="r", extra_args=[]),
            ["helm", "get", "all", "r"]
        )

        with self.assertRaises(ValueError):
            helm_cli.action_cmd("invalid", extra_args=[])

    @patch("helm_cli.subprocess.check_output")
    def test_call_global_action(self, mock_subprocess):
        mock_subprocess.return_value = "success"
        helm_cli.call_global_action(
            action="list", dry_run=False, kubeconfig=None, extra_args=["-A"]
        )
        mock_subprocess.assert_called_with(["helm", "list", "-A"], text=True)

    @patch("helm_cli.subprocess.check_output")
    @patch("helm_cli.logging.error")
    def test_call_global_action_exception(
        self, mock_logging_error, mock_subprocess
    ):
        import subprocess
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["helm"]
        )
        # Should not raise
        helm_cli.call_global_action(
            action="list", dry_run=False, kubeconfig=None, extra_args=[]
        )

        mock_subprocess.side_effect = FileNotFoundError()
        # Should not raise
        helm_cli.call_global_action(
            action="list", dry_run=False, kubeconfig=None, extra_args=[]
        )

    @patch("helm_cli.subprocess.check_output")
    @patch("helm_cli.tempfile.NamedTemporaryFile")
    def test_call_resource_action(self, mock_tempfile, mock_subprocess):
        mock_file = MagicMock()
        mock_tempfile.return_value.__enter__.return_value = mock_file
        mock_file.name = "/tmp/values.yaml"

        action = "upgrade"
        resource_type = "test-res"
        obj = {"name": "obj1"}
        parents = [{"name": "p1"}]
        extra_args = ["--dry-run"]
        _ = (obj, parents)

        helm_cli.call_resource_action(
            kubeconfig=None, action=action, resource_type=resource_type,
            resource_config={"name": "obj1"},
            release_name="p1-test-res-obj1", extra_args=extra_args
        )

        mock_file.write.assert_called()
        expected_cmd = [
            "helm", "upgrade", "--install", "p1-test-res-obj1",
            "../../charts/gdc-test-res", "-f", "/tmp/values.yaml", "--dry-run"
        ]
        mock_subprocess.assert_called_with(expected_cmd, text=True)

    @patch("helm_cli.call_resource_action")
    def test_process_type_list(self, mock_call_resource_action):
        action = "template"
        type_path = "root"
        resource_type = "my-list-res"
        type_tree = list
        config = {"my-list-res": ["item1", "item2"]}
        dry_run = False
        parents = [{"name": "root"}]
        extra_args = []

        helm_cli.process_type(
            action, type_path, resource_type, type_tree, config,
            None, None, dry_run, parents, extra_args
        )

        mock_call_resource_action.assert_called_once_with(
            kubeconfig=None,
            action=action,
            resource_type=resource_type,
            resource_config={'namespace': 'root',
                             'mylistres': ['item1', 'item2']},
            release_name='root-my-list-res',
            extra_args=extra_args
        )

    @patch("helm_cli.process_type")
    def test_process(self, mock_process_type):
        config = {"clusters": {}, "iac": {}}
        action = "template"
        dry_run = False
        api = "clusters"
        api_kubeconfig = None
        extra_args = ["--debug"]

        helm_cli.process(
            config, action, dry_run, api, api_kubeconfig, extra_args
        )
        mock_process_type.assert_called()
        _, kwargs = mock_process_type.call_args
        self.assertEqual(kwargs["action"], action)
        self.assertEqual(kwargs["extra_args"], extra_args)

    @patch("helm_cli.process_type")
    def test_process_with_api_prefix(self, mock_process_type):
        config = {"user:clstr-1": {"user-cluster-workloads": []}, "iac": {}}
        action = "template"
        helm_cli.process(
            config, action, False, "user:clstr-1", None, []
        )
        mock_process_type.assert_called()
        _, kwargs = mock_process_type.call_args
        self.assertEqual(kwargs["resource_type"], "user-cluster-workloads")
        self.assertEqual(kwargs["parents"], [
                         {'name': 'clstr-1', 'namespace': 'clstr-1'}])

    @patch("helm_cli.process_type")
    def test_process_with_global_api(self, mock_process_type):
        config = {"global": {"iam-roles": []}, "iac": {}}
        action = "template"
        helm_cli.process(
            config, action, False, "global", None, []
        )
        mock_process_type.assert_called()
        _, kwargs = mock_process_type.call_args
        self.assertEqual(kwargs["parents"], [
                         {'name': 'global', 'namespace': 'platform'}])

    def test_parse_args(self):
        sys_args = ["upgrade", "config.yaml", "--dry-run", "--set", "foo=bar"]
        args, extra = helm_cli.parse_args(sys_args)

        self.assertEqual(args.action, "upgrade")
        self.assertEqual(args.config, "config.yaml")
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.api)
        self.assertFalse(args.verbose)
        self.assertEqual(extra, ["--set", "foo=bar"])

    def test_parse_args_optional_config(self):
        sys_args = ["list", "-A"]
        args, extra = helm_cli.parse_args(sys_args)

        self.assertEqual(args.action, "list")
        self.assertIsNone(args.config)
        self.assertIsNone(args.api)
        self.assertFalse(args.verbose)
        self.assertEqual(extra, ["-A"])

    def test_parse_args_with_api_and_verbose(self):
        sys_args = [
            "validate", "config.yaml", "--api", "clusters,projects", "-v"
        ]
        args, extra = helm_cli.parse_args(sys_args)

        self.assertEqual(args.action, "validate")
        self.assertEqual(args.config, "config.yaml")
        self.assertEqual(args.api, "clusters,projects")
        self.assertTrue(args.verbose)
        self.assertEqual(extra, [])

    @patch("helm_cli.logging.error")
    @patch("helm_cli.subprocess.check_output")
    @patch("helm_cli.tempfile.NamedTemporaryFile")
    def test_call_resource_action_exception(
        self, mock_tempfile, mock_subprocess, mock_logging_error
    ):
        mock_file = MagicMock()
        mock_tempfile.return_value.__enter__.return_value = mock_file
        mock_file.name = "/tmp/values.yaml"
        import subprocess
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, ["helm"]
        )
        helm_cli.call_resource_action(
            kubeconfig=None, action="upgrade", resource_type="test-res",
            resource_config={"name": "obj1"},
            release_name="p1-test-res-obj1", extra_args=[]
        )
        mock_subprocess.side_effect = FileNotFoundError()
        helm_cli.call_resource_action(
            kubeconfig=None, action="upgrade", resource_type="test-res",
            resource_config={"name": "obj1"},
            release_name="p1-test-res-obj1", extra_args=[]
        )

    @patch("helm_cli.call_resource_action")
    def test_process_type_iac(self, mock_call_resource_action):
        helm_cli.process_type(
            "template", "root", "IAC", {}, {"iac": {"some": "iac"}},
            {"some": "iac"},
            None, False, [{"name": "root"}], []
        )
        mock_call_resource_action.assert_called_once_with(
            kubeconfig=None, action="template", resource_type="iac",
            resource_config={'namespace': 'root',
                             'iamrolebindings': {'some': 'iac'}},
            release_name='root-iac', extra_args=[]
        )

    def test_process_type_not_in_config(self):
        result = helm_cli.process_type(
            "template", "root", "missing-res", list, {"other-res": []},
            {}, None, False, [{"name": "root"}], []
        )
        self.assertIsNone(result)

    @patch("helm_cli.call_resource_action")
    def test_process_type_str_list(self, mock_call_resource_action):
        helm_cli.process_type(
            "template", "root", "my-str-res", str,
            {"my-str-res": [{"name": "o1"}]}, None, None, False,
            [{"name": "root"}], []
        )
        mock_call_resource_action.assert_called_once()

    @patch("helm_cli.call_resource_action")
    def test_process_type_str_dict(self, mock_call_resource_action):
        helm_cli.process_type(
            "template", "root", "billing", str,
            {"billing": {"accounts": {"name": "acc", "id": "123"}, "account_ref": "acc"}}, None, None, False,
            [{"name": "root"}], []
        )
        mock_call_resource_action.assert_called_once()

    @patch("helm_cli.call_resource_action")
    def test_process_type_dict(self, mock_call_resource_action):
        type_tree = {"nested-res": str}
        config = {
            "my-dict-res": [{"name": "o1", "nested-res": [{"name": "n1"}]}]
        }
        helm_cli.process_type(
            "template", "root", "my-dict-res", type_tree, config, None,
            None, False, [{"name": "root"}], []
        )
        self.assertEqual(mock_call_resource_action.call_count, 2)

    @patch("helm_cli.call_global_action")
    @patch("helm_cli.parse_args")
    def test_main_no_config(self, mock_parse_args, mock_call_global_action):
        mock_args = MagicMock()
        mock_args.action = "list"
        mock_args.config = None
        mock_args.dry_run = False
        mock_args.verbose = False
        mock_parse_args.return_value = (mock_args, ["-A"])

        with patch("helm_cli.sys.argv", ["helm_cli.py", "list", "-A"]):
            helm_cli.main()
            mock_call_global_action.assert_called_once_with(
                kubeconfig=mock_args.api_kubeconfig, action="list",
                dry_run=False, extra_args=["-A"]
            )

    @patch("helm_cli.process")
    @patch("helm_cli.yaml.safe_load")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("helm_cli.parse_args")
    def test_main_with_config(
        self, mock_parse_args, mock_open, mock_yaml_load, mock_process
    ):
        mock_args = MagicMock()
        mock_args.action = "template"
        mock_args.config = "config.yaml"
        mock_args.api = None
        mock_args.api_kubeconfig = None
        mock_args.dry_run = False
        mock_args.verbose = True
        mock_parse_args.return_value = (mock_args, [])
        mock_yaml_load.return_value = {"iac": {}}

        with patch("helm_cli.sys.argv", ["helm_cli.py", "template"]):
            helm_cli.main()
            mock_process.assert_called_once()


if __name__ == "__main__":
    unittest.main()
