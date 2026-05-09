{{/*
Common labels — used by the placeholder ConfigMap and by every future
template added when this chart is activated.
*/}}
{{- define "fluss.labels" -}}
app: fluss
app.kubernetes.io/name: fluss
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
