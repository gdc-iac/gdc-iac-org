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

    @patch("helm_cli.subprocess.check_output")
    @patch("helm_cli.tempfile.NamedTemporaryFile")
    def test_call_helm(self, mock_tempfile, mock_subprocess):
        mock_file = MagicMock()
        mock_tempfile.return_value.__enter__.return_value = mock_file
        mock_file.name = "/tmp/values.yaml"
        
        action = "upgrade"
        resource_type = "test-res"
        obj = {"name": "obj1"}
        parents = [{"name": "p1"}]
        
        helm_cli.call_helm(action, resource_type, obj, parents)
        
        mock_file.write.assert_called()
        expected_cmd = [
            "helm", "upgrade", "p1-test-res-obj1", 
            "../../charts/gdc-test-res", "-f", "/tmp/values.yaml"
        ]
        mock_subprocess.assert_called_with(expected_cmd, text=True)

    @patch("helm_cli.call_helm")
    def test_process_type_list(self, mock_call_helm):
        action = "template"
        type_path = "root"
        resource_type = "my-list-res"
        type_tree = list
        config = {"my-list-res": ["item1", "item2"]}
        dry_run = False
        parents = [{"name": "root"}]
        
        helm_cli.process_type(action, type_path, resource_type, type_tree, config, dry_run, parents)
        
        mock_call_helm.assert_called_once_with(action, resource_type, ["item1", "item2"], parents)

    @patch("helm_cli.process_type")
    def test_process(self, mock_process_type):
        config = {"clusters": {}}
        action = "template"
        dry_run = False
        
        helm_cli.process(config, action, dry_run)
        mock_process_type.assert_called()

if __name__ == "__main__":
    unittest.main()