import os

BASELINE_TEST = """suite: Baseline Rendering Test
# This is a placeholder test suite to ensure the helm-unittest pipeline runs successfully.
# Administrators should add specific logic assertions here as the templates evolve.
# Documentation: https://github.com/helm-unittest/helm-unittest
templates: []
tests: []
"""

charts_dir = "charts"
for chart_name in os.listdir(charts_dir):
    chart_path = os.path.join(charts_dir, chart_name)
    tests_dir = os.path.join(chart_path, "tests")
    
    if os.path.isdir(chart_path):
        os.makedirs(tests_dir, exist_ok=True)
        # Don't overwrite if there are already real tests mapped
        existing_tests = [f for f in os.listdir(tests_dir) if f.endswith("_test.yaml")]
        if not existing_tests:
            test_file = os.path.join(tests_dir, "baseline_test.yaml")
            with open(test_file, "w") as f:
                f.write(BASELINE_TEST)
            print(f"Generated baseline template for {chart_name}")
