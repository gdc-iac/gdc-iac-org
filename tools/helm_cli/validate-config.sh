#!/usr/bin/env bash
set -e
config=${1:?}
zone=${2:zone1}
charts_path=$(readlink -e $(dirname $0)/../)
config_file=${charts_path}/${config}.yaml
[ -f $config_file ] || { echo "No such file: $config_file"; exit 1; } 
for resource in \
 projects\
 iac-role-bindings\
 iam-roles\
 iam-role-bindings\
 ; do \
    helm template --debug ${config}-$resource ${charts_path}/gdc-$resource -f ${config_file};\
done
for resource in \
 clusters\
 buckets\
 ; do \
    helm template --debug ${config}-$resource ${charts_path}/gdc-$resource --set zone=${zone} -f ${config_file};\
done