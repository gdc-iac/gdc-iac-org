# Introduction

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
export KUBECONFIG=~/workspaces/amg1/adhoc-tools/kubeconfigs/global-api-iac-kubeconfig

# Bootstrap IaC
0. Export environment variables (example):
```
export ORG_NAME="org-1"
export IAC_PROJECT="iac-root"
export IAC_USER="fop-iac001@example.com"
```
1. Grant IaC User or Service Account required Org roles:
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

3. Grant IaC User or Service Account required `$IAC_PROJECT` roles:
```
for role in \
  secret-admin \
; do \
  gdcloud projects add-iam-policy-binding $IAC_PROJECT \
  --member=user:$IAC_USER \
  --role=$role;\
done
```
# Deploy Organization Resources
1. Configure HELM to impersonate configured user:
```
gdcloud auth login (as $IAC_USER)
gdcloud clusters get-credentials global-api
export HELM_BURST_LIMIT=1 #required in adhoc env
export HELM_NAMESPACE=$IAC_PROJECT
```

2. Validate configuration
```
export config=dga
for resource in \
 projects\
 iac-role-bindings\
 clusters\
 buckets\
 iam-roles\
 iam-role-bindings\
 ; do \
    helm template --debug ${config}-$resource ./gdc-$resource -f ${config}.yaml;\
done
```

3. Create global resources
```
export config=dga
gdcloud clusters get-credentials global-api

for resource in \
 projects\
 iac-role-bindings\
 iam-roles\
 iam-role-bindings\
 ; do \
    helm install --debug ${config}-$resource ./gdc-$resource -f ${config}.yaml;\
done
```
4. Create zonal resources 

Note: The singlezone bucket resources and clusters are created using the zonal management API endpoint.
```
export config=dga
export zone=zone1
gdcloud clusters get-credentials ${ORG_NAME}-admin --zone ${zone}

for resource in \
 clusters\
 buckets\
 ; do \
    helm install --debug ${config}-$resource ./gdc-$resource --set zone=${zone} -f ${config}.yaml;\
done

```

# Mutate Organization
Mutating organization includes operations like:
- adding projects
- removing (actually tombstoning) projects
- adding and removing users and accounts
- adding and removing roles
- adding and removing role bindings
- creating and deleting clusters
- etc

1. Configure HELM to impersonate configured user:
```
gdcloud auth login (as $IAC_USER)
gdcloud clusters get-credentials global-api
export HELM_NAMESPACE=$IAC_PROJECT
```
2. Check if authentication works:
```
helm list
```

3. Validate configuration
```
for resource in \
 projects\
 clusters\
 organization-roles\
 organization-role-bindings\
 organization-network-policies\
 project-service-accounts\
 iam-role-bindings\
 ; do \
    helm template --debug org-$resource ./gdc-$resource -f org.yaml;\
done
```
4. Update configuration
```
for resource in \
 projects\
 projectserviceaccounts\
 iamrolebindings\
 ; do \
    helm upgrade --debug org-$resource ./gdc-$resource -f org.yaml;\
done
```

# Debuging

for role in \
$(gdcloud iam roles list | grep admin)\
project-grafana-viewer \
; do \
 gdcloud organizations add-iam-policy-binding org-1 \
 --member="user:fop-platform-admin@example.com" \
 --role="$role";\
done

for role in \
$(gdcloud iam roles list | grep admin)\
project-grafana-viewer \
; do \
 gdcloud projects add-iam-policy-binding iacproj7 \
 --member="user:fop-platform-admin@example.com" \
 --role="$role";\
done


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