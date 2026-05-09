{{/*
Common labels.
*/}}
{{- define "iceberg-tools.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: iceberg-tools
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Stable selector subset.
*/}}
{{- define "iceberg-tools.selectorLabels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: iceberg-tools
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
ConfigMap name for the catalog properties. Stable name "iceberg-catalog"
so downstream consumers (flink chart, flink-cdc-jobs chart, starrocks
chart) can hardcode the reference.
*/}}
{{- define "iceberg-tools.catalogConfigMapName" -}}
iceberg-catalog
{{- end -}}
