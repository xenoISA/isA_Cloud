{{/*
postgres-dataphin is a thin wrapper around bitnami/postgresql. The bitnami
subchart owns the actual StatefulSet, Services, Secret, NetworkPolicy, and
ServiceMonitor. This file holds only the labels we'd want on any templates
we add at this layer (none today; reserved for follow-up).
*/}}
{{- define "postgres-dataphin.labels" -}}
app: postgres-dataphin
app.kubernetes.io/name: postgres-dataphin
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-dataphin-infra
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
