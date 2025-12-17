#!/usr/bin/env bash

config=${1:?}
zone=${2:zone1}
charts_path=$(readlink -e $(dirname $0)/../)
config_file=${charts_path}/${config}.yaml
[ -f $config_file ] || { echo "No such file: $config_file"; exit 1; } 
HELM_BURST_LIMIT=1 #required in adhoc env
HELM_NAMESPACE=${IAC_PROJECT:?}

gdcloud clusters get-credentials ${ORG_NAME:?}-admin --zone ${zone}

for resource in \
 buckets\
 clusters\
 ; do \
    helm install --debug ${config}-$resource ${charts_path}/gdc-$resource --set zone=${zone}  -f ${config_file};\
done