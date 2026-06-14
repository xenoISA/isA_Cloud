{{/* Standard names/labels for the Dataphin Redis chart. */}}

{{- define "redis.name" -}}
{{- default "redis" .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "redis.labels" -}}
app: {{ include "redis.name" . }}
app.kubernetes.io/name: {{ include "redis.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-dataphin-infra
app.kubernetes.io/component: cache
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "redis.selectorLabels" -}}
app: {{ include "redis.name" . }}
app.kubernetes.io/name: {{ include "redis.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Secret name that holds the redis password (existing or chart-managed). */}}
{{- define "redis.secretName" -}}
{{- if .Values.auth.existingSecret -}}
{{- .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "redis.name" .) -}}
{{- end -}}
{{- end -}}
