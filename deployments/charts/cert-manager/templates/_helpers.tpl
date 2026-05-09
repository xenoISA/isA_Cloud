{{/*
Common labels.
*/}}
{{- define "cert-manager-bigdata.labels" -}}
app: cert-manager
app.kubernetes.io/name: cert-manager
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-platform
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
