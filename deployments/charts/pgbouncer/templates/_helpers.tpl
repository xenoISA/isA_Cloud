{{/*
Common labels emitted on every resource.
*/}}
{{- define "pgbouncer.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: pgbouncer
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-platform
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels — the stable subset used in pod selectors. Must NOT change
between revisions or the Deployment selector becomes immutable.
*/}}
{{- define "pgbouncer.selectorLabels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: pgbouncer
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Name of the auth Secret. Either rendered by this chart (auth.create=true) or
pre-provisioned by the cluster operator and referenced via
auth.existingSecret.
*/}}
{{- define "pgbouncer.authSecretName" -}}
{{- if .Values.auth.existingSecret -}}
{{ .Values.auth.existingSecret }}
{{- else -}}
{{ printf "%s-auth" .Values.name }}
{{- end -}}
{{- end -}}

{{/*
Resolve the ConfigMap name for pgbouncer.ini.
*/}}
{{- define "pgbouncer.configMapName" -}}
{{ printf "%s-config" .Values.name }}
{{- end -}}
