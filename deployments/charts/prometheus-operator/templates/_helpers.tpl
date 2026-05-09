{{/*
Common labels — applied to any resources we add at this layer
(none today). The upstream chart owns the operator Deployment +
Prometheus / Grafana / AlertManager StatefulSets + CRDs; we keep
this helper for forward compatibility.
*/}}
{{- define "prometheus-operator.labels" -}}
app: prometheus-operator
app.kubernetes.io/name: prometheus-operator
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-platform
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
