{{/*
Common labels — applied to any resources we add at this layer (none today).
The upstream chart owns the operator + webhook + certController Deployments
and the CRDs.
*/}}
{{- define "external-secrets-operator.labels" -}}
app: external-secrets
app.kubernetes.io/name: external-secrets-operator
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-platform
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
