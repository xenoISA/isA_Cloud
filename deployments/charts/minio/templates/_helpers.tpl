{{/*
This chart is a thin wrapper around minio/minio. The upstream subchart
owns the Deployment / StatefulSet, Services, NetworkPolicy, PDB,
ServiceMonitor, and the post-install bucket-creation Job. We only
render an optional Secret at this layer (when auth.create=true) so the
hive-metastore S3A client has matching credentials in kind/dev.
*/}}
{{- define "minio-bigdata.labels" -}}
app: minio
app.kubernetes.io/name: minio
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
