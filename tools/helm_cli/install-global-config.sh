#!/usr/bin/env bash

config=${1:?}
charts_path=$(readlink -e $(dirname $0)/../)
config_file=${charts_path}/${config}.yaml
[ -f $config_file ] || { echo "No such file: $config_file"; exit 1; } 
HELM_BURST_LIMIT=1 #required in adhoc env
HELM_NAMESPACE=${IAC_PROJECT:?}
gdcloud clusters get-credentials global-api

for resource in \
 projects\
 iac-role-bindings\
 iam-roles\
 ; do \
    helm install --debug ${config}-$resource ${charts_path}/gdc-$resource -f ${config_file};\
done
# custom role population takes ~180s in adhoc
echo "Waiting for custom role reconciliation..."
sleep 200s
for resource in \
 iam-role-bindings\
 ; do \
    helm install --debug ${config}-$resource ${charts_path}/gdc-$resource -f ${config_file};\
done