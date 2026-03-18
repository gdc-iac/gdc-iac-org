# Example Custom Dashboards

This directory contains example Grafana dashboard templates (`.json` files) that can be imported into your Google Distributed Cloud Hosted environment.

## Available Dashboards

* **`org-vm-resources-per-project.json` (VM Resource Consumption Per Project)**
  Provides a comprehensive view of virtual machine resource allocation and consumption across your organization's projects, including CPU, Memory, Disk, and Network bandwidth usage.
  
* **`org-obj-resources-per-bucket.json` (Object Storage Resources per Bucket)**
  Monitors object storage usage at the bucket level, breaking down consumption by Standard and Nearline storage classes.

* **`org-spend-dash.json` (Organization Spend Reports)**
  Provides insights into the overall organization costs, including cumulative costs, costs by product family, and cost by month.

* **`prj-consumption-dash.json` (Project Storage and Compute Consumption)**
  Offers a detailed look at resource allocations for a specific project, including compute and storage quotas, PVCs, GPU requests, and object storage tenant quotas.

## Manually Creating Dashboards

You can manually import these dashboards into your GDC Hosted environment via the Grafana user interface.

For official documentation on creating and managing dashboards, please see the [GDC Hosted documentation on creating dashboards](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/platform/pa-user/create-dashboards).

### Import Instructions

To manually import one of these JSON dashboards:

1. Access the web interface of your GDC Hosted organization or project Observability service.
2. In the Grafana left-hand sidebar, hover over the **+** (Create) icon and select **Import**.
3. Either click **Upload JSON file** and select the `.json` file from this directory, or copy the content of the JSON file and paste it into the **Import via panel json** text box.
4. Click **Load**.
5. Adjust any names, folders, or data sources if prompted, and then click **Import**.
