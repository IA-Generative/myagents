{{/*
Expand the name of the chart.
*/}}
{{- define "mes-agents.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "mes-agents.fullname" -}}
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
{{- define "mes-agents.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mes-agents.labels" -}}
helm.sh/chart: {{ include "mes-agents.chart" . }}
{{ include "mes-agents.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.app.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mes-agents.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mes-agents.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "mes-agents.serviceAccountName" -}}
{{- if .Values.app.serviceAccount.create }}
{{- default (include "mes-agents.fullname" .) .Values.app.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.app.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image name with registry
*/}}
{{- define "mes-agents.image" -}}
{{- $registry := .Values.global.imageRegistry | default .Values.app.image.registry -}}
{{- $repository := .Values.app.image.repository -}}
{{- $tag := .Values.app.image.tag | default .Chart.AppVersion -}}
{{- printf "%s/%s:%s" $registry $repository $tag -}}
{{- end }}

{{/*
Environment variables from map
*/}}
{{- define "mes-agents.envVars" -}}
{{- range $key, $val := . }}
- name: {{ $key }}
  {{- if kindIs "map" $val }}
  {{- toYaml $val | nindent 2 }}
  {{- else }}
  value: {{ $val | quote }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
PostgreSQL secret name (from cloudpirates/postgres sub-chart)
*/}}
{{- define "mes-agents.postgresSecretName" -}}
{{- printf "%s-postgres" (include "mes-agents.fullname" .) -}}
{{- end }}

{{/*
Container env list shared by the app Deployment and the migration Job
*/}}
{{- define "mes-agents.containerEnv" -}}
{{- include "mes-agents.envVars" .Values.global.env }}
{{- /* Inject DATABASE_URL from postgres sub-chart if enabled */}}
{{- if .Values.postgres.enabled }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "mes-agents.postgresSecretName" . }}
      key: uri
{{- end }}
{{- /* Include other app env vars, excluding DATABASE_URL if postgres is enabled */}}
{{- range $key, $val := .Values.app.env }}
{{- if or (not $.Values.postgres.enabled) (ne $key "DATABASE_URL") }}
- name: {{ $key }}
  {{- if kindIs "map" $val }}
  {{- toYaml $val | nindent 2 }}
  {{- else }}
  value: {{ $val | quote }}
  {{- end }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Container envFrom list (ConfigMap / Secret) shared by the app Deployment and the migration Job
*/}}
{{- define "mes-agents.containerEnvFrom" -}}
{{- if .Values.app.envCm }}
- configMapRef:
    name: {{ include "mes-agents.fullname" . }}-env
{{- end }}
{{- if .Values.app.envSecret }}
- secretRef:
    name: {{ include "mes-agents.fullname" . }}-env
{{- end }}
{{- end }}
