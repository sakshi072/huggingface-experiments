{{/*
Expand the name of the chart.
*/}}
{{- define "retrieval-system.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "retrieval-system.fullname" -}}
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
{{- define "retrieval-system.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "retrieval-system.labels" -}}
helm.sh/chart: {{ include "retrieval-system.chart" . }}
{{ include "retrieval-system.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "retrieval-system.selectorLabels" -}}
app.kubernetes.io/name: {{ include "retrieval-system.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API labels
*/}}
{{- define "retrieval-system.api.labels" -}}
{{ include "retrieval-system.labels" . }}
app: retrieval-api
component: backend
{{- end }}

{{/*
API selector labels
*/}}
{{- define "retrieval-system.api.selectorLabels" -}}
{{ include "retrieval-system.selectorLabels" . }}
app: retrieval-api
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "retrieval-system.postgres.labels" -}}
{{ include "retrieval-system.labels" . }}
app: postgres
component: database
{{- end }}

{{/*
PostgreSQL selector labels
*/}}
{{- define "retrieval-system.postgres.selectorLabels" -}}
{{ include "retrieval-system.selectorLabels" . }}
app: postgres
{{- end }}

{{/*
MinIO labels
*/}}
{{- define "retrieval-system.minio.labels" -}}
{{ include "retrieval-system.labels" . }}
app: minio
component: storage
{{- end }}

{{/*
MinIO selector labels
*/}}
{{- define "retrieval-system.minio.selectorLabels" -}}
{{ include "retrieval-system.selectorLabels" . }}
app: minio
{{- end }}

{{/*
Redis labels
*/}}
{{- define "retrieval-system.redis.labels" -}}
{{ include "retrieval-system.labels" . }}
app: redis
component: cache
{{- end }}

{{/*
Redis selector labels
*/}}
{{- define "retrieval-system.redis.selectorLabels" -}}
{{ include "retrieval-system.selectorLabels" . }}
app: redis
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "retrieval-system.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "retrieval-system.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL hostname
*/}}
{{- define "retrieval-system.postgres.host" -}}
{{- printf "postgres-headless.%s.svc.cluster.local" .Values.global.namespace }}
{{- end }}

{{/*
MinIO hostname
*/}}
{{- define "retrieval-system.minio.host" -}}
{{- printf "minio-headless.%s.svc.cluster.local" .Values.global.namespace }}
{{- end }}

{{/*
Redis hostname
*/}}
{{- define "retrieval-system.redis.host" -}}
{{- printf "redis.%s.svc.cluster.local" .Values.global.namespace }}
{{- end }}
