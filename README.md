# Introduction

This repository provides a flexible toolkit for managing infrastructure as code (IaC) using predefined YAML configuration files and Helm charts. 

The toolkit allows you to use different tools to template and synchronize configurations based on your operational needs:

- **`helm_cli`**: A custom wrapper script for local or CI/CD usage to process configurations, template charts, and natively deploy to the cluster.
- **Helmfile**: A declarative tool for managing multiple Helm releases and enforcing deployment order.
- **Config Sync**: A GitOps operator (optional) for continuously synchronizing cluster state from this repository.
- **Charts**: A collection of local Helm charts (`charts/` directory) acting as templates for Custom Resources.
- **YAML Configs**: Unified data files (like `org.yaml` or `tenants.yaml`) used to declare the desired state of resources.
This framework is using [Helm](https://helm.sh/) as the resource config generator and can use either Helm or [Config-Sync](https://github.com/GoogleContainerTools/config-sync) as the resource state synchronization agent.

Helm creates resources in a predefined way as described in [issue/1228](https://github.com/helm/helm/issues/1228). GDCag is heavily relying on custom resources, and these are created in alphabetical order. This means that for example IAMRole resource comes before Project resource. This blocks possibility of creating single Helm Chart to manage all the resources.

Using sub-charts does not change the order as all resources are first merged into a single manifest, sorted and only uploaded afterwards. 

Using hooks solves resource creation order, however hook resources' life cycle is not managed with the release. 

Due to above, this framework is using layered approach, where single `org.yaml` configuration file is shared across multiple charts, a chart per layer. The layers are installed and updated in predefined order:
- Organization wide roles
- User Clusters [scope: zone]
- Projects
- Buckets [scope: zone]
- Project roles
- Project Service Accounts
- Role Bindings

# Setup

Helm is using the default kubeconfig path. To use different one:
```
export KUBECONFIG=<path_to_kubeconfig>
```
# Bootstrap IaC
0. Export environment variables (example):
   ```
   export ORG_NAME="org-1"
   export IAC_PROJECT="iac-root"
   export IAC_USER="fop-iac001@example.com"
   export IAC_SA="iac001-sa"
   export GDCH_DOMAIN="google.gdch.test"
   export ZONE="zone1"
   export GDCH_CONSOLE="console.${ORG_NAME}.${ZONE}.${GDCH_DOMAIN}"
   ```
1. Grant IaC Bootstrap User required Org roles:
   ```
   for role in \
   organization-iam-admin \
   project-creator \
   project-editor \
   user-cluster-admin \
   ; do \
      gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
      --member="user:$IAC_USER" \
      --role="$role";\
   done
   ```
2. Create a project to host IaC resources

   ```
   gdcloud auth login (as $IAC_USER)
   gdcloud projects create $IAC_PROJECT
   ```

3. Grant IaC Bootstrap User required `$IAC_PROJECT` roles:
   ```
   for role in \
   secret-admin \
   project-iam-admin \
   ; do \
   gdcloud projects add-iam-policy-binding $IAC_PROJECT \
   --member=user:$IAC_USER \
   --role=$role;\
   done
   ```

4. Follow [documentation](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#gdcloud) to create service account:
   ```
   gdcloud iam service-accounts create $IAC_SA --project $IAC_PROJECT
   ```

5. Assign the permissions required by the service account:
- organization:
   ```
   for role in \
   organization-iam-admin \
   project-creator \
   project-editor \
   user-cluster-admin \
   ; do \
      gdcloud organizations add-iam-policy-binding "$ORG_NAME" \
      --member="serviceAccount:$IAC_PROJECT:$IAC_SA" \
      --role="$role";\
   done
   ```
- project:
   ```
   for role in \
   secret-admin \
   ; do \
   gdcloud projects add-iam-policy-binding $IAC_PROJECT \
   --member="serviceAccount:$IAC_PROJECT:$IAC_SA" \
   --role=$role;\
   done
   ```
6. Obtain the Service Account [credentials](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#create-and-add-key-pairs):
   ```
   gdcloud iam service-accounts keys create ${IAC_PROJECT}_${IAC_SA}.json \
      --project=${IAC_PROJECT} \
      --iam-account=$IAC_SA
   ```

7. [Generate kubeconfig](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/iam/service-identities#generate-kubeconfig) file:
   ```
   gdcloud auth activate-service-account --key-file=${IAC_PROJECT:?}_${IAC_SA:?}.json
   gdcloud auth print-identity-token --audiences=https://global-api.${ORG_NAME:?}.${ZONE:?}.${GDCH_DOMAIN:?}
   
   gdcloud auth print-identity-token --audiences=https://management-kube.apiserver.${ORG_NAME:?}.${ZONE:?}.${GDCH_DOMAIN:?} --zone=${ZONE:?}
   export KUBECONFIG=${IAC_PROJECT:?}_${IAC_SA:?}-global-api.kubeconfig
   gdcloud clusters get-credentials global-api
   export KUBECONFIG=${IAC_PROJECT:?}_${IAC_SA:?}-${ZONE:?}.kubeconfig
   gdcloud clusters get-credentials ${ORG_NAME:?}-admin --zone ${ZONE:?}
   ```

# Manage Organization Resources using HELM CLI

You can manage and deploy resources using our custom `helm_cli.py` wrapper tool. It provides a convenient way to validate, template, and deploy Helm charts based on a unified configuration.

For full usage instructions, examples, and testing details, please refer to the dedicated [Helm CLI README](./tools/helm_cli/README.md).

# Manage Organization Resources using HELMFILE

Helmfile is a declarative tool for managing multiple Helm releases, allowing you to orchestrate the deployment of the entire GDC resources suite efficiently. It relies on a `tenants.yaml` configuration to dynamically generate the required Helm releases in the correct order.

For a comprehensive guide, architecture diagram, and deployment instructions using Helmfile, please refer to the dedicated [Helmfile README](./tools/helmfile/README.md).

# Notes
- https://github.com/helm/helm/issues/1228

# GDCag Resource Creation
## Zonal resource creation sequence
- clusters.cluster.gdc.goog: [only zonal mgmt]
- OrganizationNetworkPolicy: [only zonal mgmt]
## Global Resource creation sequence:
- projects namespace: platform
- customroles.iam.global.gdc.goog namespace: platform
- projectserviceaccounts.resourcemanager.global.gdc.goog namespace: project
- iamrolebindings.iam.global.gdc.goog namespace: platform/project-name (both regular and custom)
- projectnetworkpolicies.networking.global.gdc.goog namespace: project

# Global resources
- backendservicepolicies.networking.global.gdc.goog                                  
- backendservices.networking.global.gdc.goog                                         
- billingaccountbindings.billing.global.gdc.goog                                     
- billingaccounts.billing.global.gdc.goog                                            
- blockinvalidgdchrestrictedservice.constraints.global.gatekeeper.sh                 
- bucketinfos.object.global.private.gdc.goog                                         
- bucketlocationconfigs.object.global.gdc.goog                                       
- bucketlocations.object.global.gdc.goog                                             
- buckets.object.global.gdc.goog                                                     
- clustermeshes.network.global.private.gdc.goog                                      
- customroles.iam.global.gdc.goog                                                    
- datasources.monitoring.global.private.gdc.goog                                     
- dnsregistrations.network.global.private.gdc.goog                                   
- dnszones.network.global.private.gdc.goog                                           
- etcdcarotations.etcd.mz.global.private.gdc.goog                                    
- etcdclusterconfigoverrides.etcd.mz.global.private.gdc.goog                         
- etcdclusters.etcd.mz.global.private.gdc.goog                                       
- etcdzones.etcd.mz.global.private.gdc.goog                                          
- forwardingruleexternals.networking.global.gdc.goog                                 
- forwardingruleinternals.networking.global.gdc.goog                                 
- gdchallowedchars.constraints.global.gatekeeper.sh                                  
- gdchallowedlength.constraints.global.gatekeeper.sh                                 
- gdchallowednamespaces.constraints.global.gatekeeper.sh                             
- gdchreadonly.constraints.global.gatekeeper.sh                                      
- gdchreservednames.constraints.global.gatekeeper.sh                                 
- gdchreservedprefix.constraints.global.gatekeeper.sh                                
- gdchreservedsuffix.constraints.global.gatekeeper.sh                                
- gdchrestrictattribute.constraints.global.gatekeeper.sh                             
- gdchrestrictattributerange.constraints.global.gatekeeper.sh                        
- gdchrestrictbyattributes.constraints.global.gatekeeper.sh                          
- gdchrestrictedservice.constraints.global.gatekeeper.sh                             
- gdchrestrictfinalizerremoval.constraints.global.gatekeeper.sh                      
- gdchrestrictobjectstorageattributevalue.constraints.global.gatekeeper.sh           
- gdchrestrictresource.constraints.global.gatekeeper.sh                              
- gdchsuffixednamespace.constraints.global.gatekeeper.sh                             
- gdchsystemclusterresource.constraints.global.gatekeeper.sh                         
- globaladdresspoolclaims.ipam.global.private.gdc.goog                               
- globaladdresspools.ipam.global.private.gdc.goog                                    
- globalapizones.location.mz.global.private.gdc.goog                                 
- globalresourceregistrations.apiregistry.global.private.gdc.goog                    
- globalrootkeys.kms.global.private.gdc.goog                                         
- globalsecrets.core.global.private.gdc.goog                                         
- healthchecks.networking.global.gdc.goog                                            
- iamrolebindings.iam.global.gdc.goog                                                
- iamroles.iam.global.gdc.goog                                                       
- identityproviderconfigs.iam.global.gdc.goog                                        
- ioauthmethods.iam.global.private.gdc.goog                                          
- kubeapiservers.lcm.global.private.gdc.goog                                         
- manageddnszones.networking.global.gdc.goog                                         
- mzaeadkeys.kms.global.gdc.goog                                                     
- orgbootstraps.bootstrap.mz.global.private.gdc.goog                                 
- orgzones.bootstrap.mz.global.private.gdc.goog                                      
- projectnetworkpolicies.networking.global.gdc.goog                                  
- projects.resourcemanager.global.gdc.goog                                           
- projectserviceaccounts.resourcemanager.global.gdc.goog                             
- releases.release.mz.global.private.gdc.goog                                        
- resourcerecordsets.network.global.private.gdc.goog                                 
- resourcerecordsets.networking.global.gdc.goog                                      
- subnets.ipam.global.gdc.goog                                                       
- tokenrequests.bootstrap.mz.global.private.gdc.goog                                 
- virtualmachineimages.virtualmachine.global.gdc.goog                                
- volumereplicationrelationships.storage.global.gdc.goog                             
- zonalrolebindings.iam.global.gdc.goog                                              
- zonednsservers.network.global.private.gdc.goog                                     
- zoneexclusions.location.mz.global.private.gdc.goog                                 
- zones.location.mz.global.private.gdc.goog                                          
- zoneselectionresults.location.mz.global.private.gdc.goog                           
- zoneselections.location.mz.global.private.gdc.goog                                 
