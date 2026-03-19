import os
import json

charts_dir = "charts"
for chart_name in os.listdir(charts_dir):
    chart_path = os.path.join(charts_dir, chart_name)
    values_file = os.path.join(chart_path, "values.yaml")
    
    if os.path.isdir(chart_path) and os.path.isfile(values_file):
        properties = {}
        with open(values_file, "r") as f:
            for line in f:
                if not line.startswith(" ") and not line.startswith("#") and not line.startswith("-") and ":" in line:
                    key = line.split(":")[0].strip()
                    if key and not key.startswith("{") and not key.startswith("["):
                        # Accept any type for the property to serve as a baseline structural schema
                        properties[key] = {}
        
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": f"Values schema for {chart_name}",
            "type": "object",
            "properties": properties
        }
        
        schema_file = os.path.join(chart_path, "values.schema.json")
        with open(schema_file, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"Generated {schema_file}")
