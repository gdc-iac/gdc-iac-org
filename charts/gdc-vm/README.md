# GDC Virtual Machine Helm Chart

This Helm chart deploys and manages Google Distributed Cloud (GDC) virtual machines on versions 1.11.x and greater.

## APIs Used

- `virtualmachine.gdc.goog/v1` for creating and managing `VirtualMachine` resources (`gvm`)
- `virtualmachine.gdc.goog/v1` for creating and managing `VirtualMachineDisk` resources (`gDisk`)

## Prerequisites

- Helm v3.0+
- Access to a GDC environment (version 1.11.x or greater)

## Installing the Chart

To install the chart with the release name `my-release`:

```bash
helm install my-release ./gdc-vm -f ./gdc-vm/values.yaml -n "projectname"

For example, to deploy a vm to a project called "test", use the command 

helm install my-release ./gdc-vm -f ./gdc-vm/values.yaml -n test
```
PLEASE NOTE: Due to resource crunch at the sandbox level, sometimes the VMs are deployed with "Error". 
In that case, verify the VM state by using 

```bash
kubectl describe Virtualmachine
```
 If the Status.State message is: ErrorUnschedulable, wait for a couple of hours for the VM to be deployed (typically 2 - 9 hours). 
 
## Uninstalling the Chart

To uninstall/delete the `my-release` deployment:

```bash
helm uninstall my-release
```

This command removes all the Kubernetes components associated with the chart and deletes the release.

## Configuration

Refer to the `values.yaml` file for detailed configuration options. Key configurable parameters include:

- VM name and namespace
- Image name and namespace
- Boot disk size and auto-delete behavior
- Machine type
- Ingress and egress settings
- Secure boot option
- SSH access settings

## Example Configurations

### Minimal Configuration

```yaml
virtualMachines:
  - name: minimal-vm
    namespace: default
    imageName: rocky-8-v20231229-gdch
    imageNamespace: vm-system
    bootDiskSize: 20Gi
    machineType: n2-standard-2-gdc
```

### Advanced Configuration

```yaml
virtualMachines:
  - name: advanced-vm
    namespace: project-x
    imageName: ubuntu-20-04-v20240101-gdch
    imageNamespace: vm-system
    bootDiskSize: 50Gi
    machineType: n2-highmem-8-gdc
    ingressEnabled: true
    egressEnabled: true
    enableSecureBoot: true
    bootDiskAutoDelete: false
    ssh:
      uiAccessEnabled: true
      createProjectNetworkPolicy: true
      externalAccess:
        enabled: true
        publicKey: "ssh-rsa AAAAB3NzaC1yc2EAAAADAQA..."
        ttl: "12h"
        user: "admin-user"
```

## Features

**VM Image:**

- Specify the desired image for your VM. List available images with:

  ```bash
  kubectl get virtualmachineimages.virtualmachine.gdc.goog -n vm-system
  ```

**Boot Disk:**

- Configure the size and auto-delete behavior of the boot disk.

**Machine Type:**

- Choose from available options like `n2-standard-2-gdc`, `n2-standard-4-gdc`, etc..

**SSH Access:**

- Configure UI access and create necessary network policies
- Set up external SSH access with public key

## Generated Resources

The chart will generate the following resources based on your configuration:

**ProjectNetworkPolicy:** Created when UI SSH access is enabled and `createProjectNetworkPolicy` is true.
**VirtualMachineExternalAccess:** Created when UI SSH access is enabled.
**VirtualMachineAccessRequest:** Created when external SSH access is enabled _and_ a public key is provided.

## SSH Access

If `ssh.uiAccessEnabled` is set to `true`, the Helm chart will automatically create a
`ProjectNetworkPolicy` named `<$vm-name>-allow-ssh-ingress` to allow ingress
traffic on TCP port 22 from any IP address (`0.0.0.0/0`). This policy is
required for accessing the virtual machine using the SSH button in the GDC UI.

**Note:** Allowing ingress from `0.0.0.0/0` permits access from any IP address.
Consider restricting the ingress to specific IP ranges for better security.

### Generating SSH Keys

To generate an SSH key pair to access your VM from an external machine (not via the console UI):

1. Open a terminal on your local machine.
2. Run the following command, replacing `<$vm-name>` with your desired name:

   ```bash
   ssh-keygen -t rsa -b 4096 -f ~/<$vm-name>-access
   ```

3. When prompted, you can enter a passphrase or leave it empty for no
passphrase.

This command generates two files:

- `~/<$vm-name>-access`: The private key (**keep this secure and do not share**)
- `~/<$vm-name>-access.pub`: The public key (_use this in your Helm values file_)

### External SSH Access and 24-Hour Limit

When external SSH access is enabled, a `VirtualMachineAccessRequest` (VMAR) is
created with a time-to-live (TTL) of 24 hours. After this period, the SSH access
will expire and the key will be deleted.

**Note:** 24 Hour is the _max allowable value_ for the TTL of this access request.

To setup initial SSH access:

1. Generate an SSH key pair as described above.
2. Copy the contents of the public key file (`~/<$vm-name>-access.pub`).
3. Update your values.yaml file, setting `ssh.externalAccess.enabled` to true and pasting the public key content into ssh.externalAccess.publicKey.

Install the chart using:

```bash
helm install <release-name> /gdc-vm -f values.yaml
```

To refresh SSH access:

1. With inital access already setup as described above, just run a Helm upgrade command:

```bash
helm upgrade <release-name> gdc-vm
```

This upgrade process will:

- Leave the existing VM untouched (if no VM spec changes are made)
- Generate a new VMAR with a fresh 24-hour TTL

You can run this upgrade command as often as needed to refresh SSH access
without affecting the VM itself. Each upgrade creates a new VMAR with a unique name,
ensuring updated access when old VMARs expire after 24 hours.

This _functionally idempotent_ SSH access refresh mechanism allows for easy
maintenance of SSH access without modifying the VM, providing a consistent user
experience for access management.

#### Notes

- Ensure that the specified image and namespace exist in your GDC environment.
- The `ssh.externalAccess.publicKey` should be a valid SSH public key.
- The `ssh.externalAccess.ttl` value should not exceed 24 hours.

For more information on available machine types and images, refer to the GDC documentation.