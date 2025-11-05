# Setup

Helm is using the default kubeconfig path. Setup to use the same 
export KUBECONFIG=~/workspaces/amg1/adhoc-tools/kubeconfigs/global-api-iac-kubeconfig

# Grant roles to IaC User

for role in \
organization-iam-admin \
project-creator \
project-editor \
user-cluster-admin \
; do \
 gdcloud organizations add-iam-policy-binding org-1 \
 --member="user:fop-iac001@example.com" \
 --role="$role";\
done

gdcloud auth login (as fop-iac001@example.com)
gdcloud projects create iac-root

for role in \
secret-admin \
; do \
gdcloud projects add-iam-policy-binding iac-root \
--member=user:fop-iac001@example.com \
--role=$role;\
done

# Deploy Org Resources
export KUBECONFIG=~/workspaces/amg1/adhoc-tools/kubeconfigs/global-api-kubeconfig
export HELM_NAMESPACE=iac-root
helm list

for resource in \
 projects\
 projectserviceaccounts\
 iamrolebindings\
 ; do \
    helm template --debug org-$resource ./gdc-$resource -f org.yaml;\
done


for resource in \
 projects\
 projectserviceaccounts\
 iamrolebindings\
 ; do \
    helm install --debug org-$resource ./gdc-$resource -f org.yaml;\
done

for resource in \
 projects\
 projectserviceaccounts\
 iamrolebindings\
 ; do \
    helm upgrade --debug org-$resource ./gdc-$resource -f org.yaml;\
done

# Update Project
helm upgrade --debug iacproj1 ./gdc-project -f projects.yaml


# Debug

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