{{- define "ollama.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ollama.fullname" -}}
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

{{- define "ollama.namespace" -}}
{{- if .Values.global.namespace -}}
{{- .Values.global.namespace -}}
{{- else if .Values.namespace -}}
{{- .Values.namespace -}}
{{- else if ne .Release.Namespace "default" -}}
{{- .Release.Namespace -}}
{{- else -}}
gemma-inference
{{- end -}}
{{- end -}}

{{- define "ollama.image" -}}
{{- $repo := .Values.image.repository -}}
{{- $globalReg := .Values.global.registry -}}
{{- if and $globalReg (or (eq $repo "ollama/ollama") (hasPrefix "harbor.gdc.local/" $repo)) -}}
{{- printf "%s/%s:%s" (trimSuffix "/" $globalReg) (base $repo) (.Values.image.tag | default "0.20.2") -}}
{{- else -}}
{{- printf "%s:%s" $repo (.Values.image.tag | default "0.20.2") -}}
{{- end -}}
{{- end -}}

{{- define "ollama.labels" -}}
app.kubernetes.io/name: {{ include "ollama.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

