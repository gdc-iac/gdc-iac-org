# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0.

{{- define "p14-antigravity-dev.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "p14-antigravity-dev.namespace" -}}
{{- coalesce .Values.global.namespace .Values.namespace .Release.Namespace }}
{{- end }}

{{- define "p14-antigravity-dev.projectId" -}}
{{- coalesce .Values.global.projectId .Values.global.namespace .Values.namespace .Release.Namespace }}
{{- end }}

{{- define "p14-antigravity-dev.registry" -}}
{{- coalesce .Values.global.registry .Values.registry "harbor.gdc.local/blueprint-images" }}
{{- end }}

{{- define "p14-antigravity-dev.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name (.Chart.Version | replace "+" "_") }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: "p14-antigravity-dev"
app.kubernetes.io/instance: {{ .Release.Name }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{- define "p13-gdc-dev.namespace" -}}
{{- include "p14-antigravity-dev.namespace" . }}
{{- end }}

{{- define "p13-gdc-dev.registry" -}}
{{- include "p14-antigravity-dev.registry" . }}
{{- end }}

{{- define "p13-gdc-dev.labels" -}}
{{- include "p14-antigravity-dev.labels" . }}
{{- end }}
