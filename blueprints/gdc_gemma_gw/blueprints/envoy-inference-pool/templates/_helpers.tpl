{{- define "envoy-inference-pool.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "envoy-inference-pool.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "envoy-inference-pool.namespace" -}}
{{- coalesce .Values.global.namespace .Values.namespace .Release.Namespace -}}
{{- end -}}

{{- define "envoy-inference-pool.eppImage" -}}
{{- $repo := .Values.epp.image.repository -}}
{{- $reg := coalesce .Values.registry .Values.global.registry -}}
{{- if and $reg (or (hasPrefix "registry.k8s.io/" $repo) (hasPrefix "harbor.gdc.local/" $repo)) -}}
{{- printf "%s/%s:%s" (trimSuffix "/" $reg) (base $repo) (.Values.epp.image.tag | default "v1.3.0") -}}
{{- else -}}
{{- printf "%s:%s" $repo (.Values.epp.image.tag | default "v1.3.0") -}}
{{- end -}}
{{- end -}}

{{- define "envoy-inference-pool.labels" -}}
app.kubernetes.io/name: {{ include "envoy-inference-pool.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}
