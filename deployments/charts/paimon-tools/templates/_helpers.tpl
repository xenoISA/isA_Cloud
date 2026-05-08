{{/*
Common labels.
*/}}
{{- define "paimon-tools.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: paimon-tools
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Stable selector subset.
*/}}
{{- define "paimon-tools.selectorLabels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: paimon-tools
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
ConfigMap name for the catalog properties.
*/}}
{{- define "paimon-tools.catalogConfigMapName" -}}
paimon-catalog
{{- end -}}
