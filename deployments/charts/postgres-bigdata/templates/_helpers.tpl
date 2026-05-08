{{/*
postgres-bigdata is a thin wrapper around bitnami/postgresql. The bitnami
subchart owns the actual StatefulSet, Services, Secret, NetworkPolicy, and
ServiceMonitor. This file holds only the labels we'd want on any
templates we add at this layer (none today; reserved for follow-up).
*/}}
{{- define "postgres-bigdata.labels" -}}
app: postgres-bigdata
app.kubernetes.io/name: postgres-bigdata
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
