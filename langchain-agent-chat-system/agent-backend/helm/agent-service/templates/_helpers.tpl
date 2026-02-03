{{/*
Expand the name of the chart.
*/}}
{{- define "agent-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "agent-service.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "agent-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "agent-service.labels" -}}
helm.sh/chart: {{ include "agent-service.chart" . }}
{{ include "agent-service.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "agent-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API labels
*/}}
{{- define "agent-service.api.labels" -}}
{{ include "agent-service.labels" . }}
app: langchain-backend
component: backend
{{- end }}

{{/*
API selector labels
*/}}
{{- define "agent-service.api.selectorLabels" -}}
{{ include "agent-service.selectorLabels" . }}
app: langchain-backend
{{- end }}

{{/*
RAGAPI selector labels
*/}}
{{- define "agent-service.ragapi.selectorLabels" -}}
{{ include "agent-service.selectorLabels" . }}
app: retrieval-api
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "agent-service.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "agent-service.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
