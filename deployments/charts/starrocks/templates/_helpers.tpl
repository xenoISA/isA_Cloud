{{/*
Common labels.
*/}}
{{- define "starrocks-bigdata.labels" -}}
app: starrocks
app.kubernetes.io/name: starrocks
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
