{{/* Chart name (overridable). */}}
{{- define "querywise.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully-qualified release name. */}}
{{- define "querywise.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "querywise.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels. */}}
{{- define "querywise.labels" -}}
helm.sh/chart: {{ include "querywise.chart" . }}
{{ include "querywise.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels (app-wide). */}}
{{- define "querywise.selectorLabels" -}}
app.kubernetes.io/name: {{ include "querywise.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Per-component selector labels. Pass a dict: (dict "ctx" . "component" "backend"). */}}
{{- define "querywise.componentSelectorLabels" -}}
{{ include "querywise.selectorLabels" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Service account name. */}}
{{- define "querywise.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "querywise.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Name of the Secret to read env from (existing or chart-created). */}}
{{- define "querywise.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "querywise.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/* Name of the ConfigMap to read env from. */}}
{{- define "querywise.configMapName" -}}
{{- printf "%s-config" (include "querywise.fullname" .) -}}
{{- end -}}

{{/* Image refs (tag defaults to appVersion). */}}
{{- define "querywise.backendImage" -}}
{{- $tag := default .Chart.AppVersion .Values.image.backend.tag -}}
{{- printf "%s:%s" .Values.image.backend.repository $tag -}}
{{- end -}}

{{- define "querywise.frontendImage" -}}
{{- $tag := default .Chart.AppVersion .Values.image.frontend.tag -}}
{{- printf "%s:%s" .Values.image.frontend.repository $tag -}}
{{- end -}}

{{/* envFrom block shared by backend, worker, and migrate. */}}
{{- define "querywise.envFrom" -}}
- configMapRef:
    name: {{ include "querywise.configMapName" . }}
- secretRef:
    name: {{ include "querywise.secretName" . }}
{{- end -}}
