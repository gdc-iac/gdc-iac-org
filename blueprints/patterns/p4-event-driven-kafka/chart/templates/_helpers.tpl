# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

{{/*
Expand the name of the chart.
*/}}
{{- define "p4-event-driven-kafka.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "p4-event-driven-kafka.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Resolve target namespace: prefers global.namespace, then namespace, then Release.Namespace.
*/}}
{{- define "p4-event-driven-kafka.namespace" -}}
{{- coalesce .Values.global.namespace .Values.namespace .Release.Namespace }}
{{- end }}

{{/*
Resolve GDC project ID: prefers global.projectId, then global.namespace.
*/}}
{{- define "p4-event-driven-kafka.projectId" -}}
{{- coalesce .Values.global.projectId .Values.global.namespace .Values.namespace .Release.Namespace }}
{{- end }}

{{/*
Resolve container image registry prefix.
*/}}
{{- define "p4-event-driven-kafka.registry" -}}
{{- coalesce .Values.global.registry .Values.registry "harbor.gdc.local/blueprint-images" }}
{{- end }}

{{/*
Common labels applied to all pattern resources.
*/}}
{{- define "p4-event-driven-kafka.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name (.Chart.Version | replace "+" "_") }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: "p4-event-driven-kafka"
app.kubernetes.io/instance: {{ .Release.Name }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}
