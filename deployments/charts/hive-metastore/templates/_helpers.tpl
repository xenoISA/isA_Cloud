{{/*
Common labels.
*/}}
{{- define "hms.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: hive-metastore
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels — stable subset for pod selection.
*/}}
{{- define "hms.selectorLabels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: hive-metastore
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Resolve the DB Secret name. Either rendered by this chart (db.auth.create=true)
or referenced via db.auth.existingSecret.
*/}}
{{- define "hms.dbSecretName" -}}
{{- if .Values.db.auth.existingSecret -}}
{{ .Values.db.auth.existingSecret }}
{{- else -}}
{{ printf "%s-db" .Values.name }}
{{- end -}}
{{- end -}}

{{/*
Resolve the S3A Secret name (for fs.s3a.access.key / secret.key).
*/}}
{{- define "hms.s3aSecretName" -}}
{{- if .Values.s3a.auth.existingSecret -}}
{{ .Values.s3a.auth.existingSecret }}
{{- else -}}
{{ printf "%s-s3a" .Values.name }}
{{- end -}}
{{- end -}}

{{/*
ConfigMap name for hive-site.xml.
*/}}
{{- define "hms.configMapName" -}}
{{ printf "%s-config" .Values.name }}
{{- end -}}

{{/*
Build the JDBC URL the Hive Metastore reads on startup.
*/}}
{{- define "hms.jdbcUrl" -}}
jdbc:postgresql://{{ .Values.db.host }}:{{ .Values.db.port }}/{{ .Values.db.name }}
{{- end -}}
