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
 iam-role-bindings\
 ; do \
    helm upgrade --debug ${config}-$resource ${charts_path}/gdc-$resource -f ${config_file};\
done