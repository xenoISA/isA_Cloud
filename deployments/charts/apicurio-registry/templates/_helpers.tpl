{{/*
Common labels.
*/}}
{{- define "apicurio.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: apicurio-registry
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels — stable subset.
*/}}
{{- define "apicurio.selectorLabels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: apicurio-registry
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Resolve the DB Secret name. Either rendered by this chart (db.auth.create=true)
or referenced via db.auth.existingSecret.
*/}}
{{- define "apicurio.dbSecretName" -}}
{{- if .Values.db.auth.existingSecret -}}
{{ .Values.db.auth.existingSecret }}
{{- else -}}
{{ printf "%s-db" .Values.name }}
{{- end -}}
{{- end -}}

{{/*
JDBC URL assembled from db.{host,port,name}. Apicurio expects a full JDBC
URL in REGISTRY_DATASOURCE_URL.
*/}}
{{- define "apicurio.jdbcUrl" -}}
jdbc:postgresql://{{ .Values.db.host }}:{{ .Values.db.port }}/{{ .Values.db.name }}
{{- end -}}
