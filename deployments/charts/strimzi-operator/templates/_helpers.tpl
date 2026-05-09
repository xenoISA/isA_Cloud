{{/*
Common labels — used only on resources we add at this layer (none today).
The upstream chart owns the operator Deployment, RBAC, and CRDs; we
keep this helper for forward compatibility (future overlays can wrap
it).
*/}}
{{- define "strimzi-operator.labels" -}}
app: strimzi-operator
app.kubernetes.io/name: strimzi-operator
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
