import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
import logging
import yaml

# Add the directory containing helm_cli.py to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import helm_cli

class TestHelmCli(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None

    def test_resource_config_buckets(self):
        resource_type = "buckets"
        obj = {"name": "my-bucket", "location": "us-west1"}
        parents = [{"name": "my-project"}]
        
        expected = {
            "buckets": [{
                "name": "my-bucket", 
                "location": "us-west1", 
                "namespace": "my-project"
            }]
        }
        
        result = helm_cli.resource_config(resource_type, obj, parents)
        self.assertEqual(result, expected)

    def test_resource_config_buckets_inherit_location(self):
        resource_type = "buckets"
        obj = {"name": "my-bucket"}
        # parents[0] is the root api
        parents = [{"name": "global-region"}, {"name": "my-project"}]
        
        expected = {
            "buckets": [{
                "name": "my-bucket", 
                "location": "global-region", 
                "namespace": "my-project"
            }]
        }
        
        result = helm_cli.resource_config(resource_type, obj, parents)
        self.assertEqual(result, expected)

    def test_resource_config_iam_role_bindings(self):
        resource_type = "iam-role-bindings"
        obj = [{"role": "roles/storage.admin", "member": "user:test@example.com"}]
        parents = [{"name": "my-project"}]
        
        expected = {
            "namespace": "my-project",
            "iamrolebindings": obj
        }
        
        result = helm_cli.resource_config(resource_type, obj, parents)
        self.assertEqual(result, expected)

    def test_resource_config_generic(self):
        resource_type = "some-resource"
        obj = {"name": "res1", "prop": "val"}
        parents = [{"name": "parent1"}]
        
        expected = {
            "someresource": [obj]
        }
        
        result = helm_cli.resource_config(resource_type, obj, parents)
        self.assertEqual(result, expected)

    def test_release_name_dict(self):
        resource_type = "my-res"
        obj = {"name": "obj1"}
        parents = [{"name": "parent1"}]
        
        result = helm_cli.release_name(resource_type, obj, parents)
        self.assertEqual(result, "parent1-my-res-obj1")

    def test_release_name_list(self):
        resource_type = "my-res"
        obj = ["item1", "item2"]
        parents = [{"name": "parent1"}]
        
        result = helm_cli.release_name(resource_type, obj, parents)
        self.assertEqual(result, "parent1-my-res")

    def test_action_cmd_upgrade(self):
        action = "upgrade"
        release = "my-release"
        chart = "my-chart"
        values = "values.yaml"
        extra = ["--wait", "--timeout", "10m"]
        
        expected = ["helm", "upgrade", "--install", release, chart, "-f", values, "--wait", "--timeout", "10m"]
        result = helm_cli.action_cmd(action, release_name=release, chart=chart, values_file=values, extra_args=extra)
        self.assertEqual(result, expected)

    def test_action_cmd_list(self):
        action = "list"
        extra = ["-A"]
        expected = ["helm", "list", "-A"]
        result = helm_cli.action_cmd(action, extra_args=extra)
        self.assertEqual(result, expected)

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
        
        helm_cli.call_resource_action(action, resource_type, obj, parents, extra_args)
        
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
        
        helm_cli.process_type(action, type_path, resource_type, type_tree, config, dry_run, parents, extra_args)
        
        mock_call_resource_action.assert_called_once_with(action, resource_type, ["item1", "item2"], parents, extra_args)

    @patch("helm_cli.process_type")
    def test_process(self, mock_process_type):
        config = {"clusters": {}}
        action = "template"
        dry_run = False
        extra_args = ["--debug"]
        
        helm_cli.process(config, action, dry_run, extra_args)
        mock_process_type.assert_called()
        args, _ = mock_process_type.call_args
        self.assertEqual(args[0], action)
        self.assertEqual(args[7], extra_args)

    def test_parse_args(self):
        sys_args = ["upgrade", "config.yaml", "--dry-run", "--set", "foo=bar"]
        args, extra = helm_cli.parse_args(sys_args)
        
        self.assertEqual(args.action, "upgrade")
        self.assertEqual(args.config, "config.yaml")
        self.assertTrue(args.dry_run)
        self.assertEqual(extra, ["--set", "foo=bar"])

    def test_parse_args_optional_config(self):
        sys_args = ["list", "-A"]
        args, extra = helm_cli.parse_args(sys_args)
        
        self.assertEqual(args.action, "list")
        self.assertIsNone(args.config)
        self.assertEqual(extra, ["-A"])

if __name__ == "__main__":
    unittest.main()