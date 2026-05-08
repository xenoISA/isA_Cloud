{{/*
Common labels emitted on every resource. Strimzi adds its own
`strimzi.io/cluster` label on managed pods; do not duplicate it here.
*/}}
{{- define "kafka.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: kafka
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels — stable subset for pod selection. Strimzi pods carry
`strimzi.io/cluster: <name>`, so NetworkPolicy / ServiceMonitor selectors
should use that label, not the helm-managed `app` label.
*/}}
{{- define "kafka.strimziSelector" -}}
strimzi.io/cluster: {{ .Values.name }}
{{- end -}}

{{/*
Resolve the metrics ConfigMap name. When metrics.configMapName is empty
the chart renders one under `<name>-metrics`; otherwise the operator must
have pre-provisioned a ConfigMap at the given name with key
.Values.metrics.configMapKey.
*/}}
{{- define "kafka.metricsConfigMapName" -}}
{{- if .Values.metrics.configMapName -}}
{{ .Values.metrics.configMapName }}
{{- else -}}
{{ printf "%s-metrics" .Values.name }}
{{- end -}}
{{- end -}}
