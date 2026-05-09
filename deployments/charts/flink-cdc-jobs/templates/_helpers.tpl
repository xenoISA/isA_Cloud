{{/*
Common labels — applied to ConfigMaps and FlinkSessionJob CRs.
*/}}
{{- define "flink-cdc-jobs.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: flink-cdc-jobs
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Per-source labels: same base + a source name marker.
*/}}
{{- define "flink-cdc-jobs.sourceLabels" -}}
{{- $ := index . 0 -}}
{{- $source := index . 1 -}}
{{ include "flink-cdc-jobs.labels" $ }}
flink-cdc-source: {{ $source.name }}
{{- end -}}

{{/*
DNS-safe form of a source name. Source names mirror sn-commercial-tower
data_platform/sources/ filenames which use underscores; K8s names
follow RFC 1123 (lowercase alphanumeric + hyphens), so we transliterate.
*/}}
{{- define "flink-cdc-jobs.dnsName" -}}
{{- . | lower | replace "_" "-" -}}
{{- end -}}

{{/*
ConfigMap name for a given source.
*/}}
{{- define "flink-cdc-jobs.configMapName" -}}
{{- $ := index . 0 -}}
{{- $source := index . 1 -}}
{{ printf "%s-%s-sql" $.Values.configMapPrefix (include "flink-cdc-jobs.dnsName" $source.name) }}
{{- end -}}

{{/*
FlinkSessionJob name for a given source.
*/}}
{{- define "flink-cdc-jobs.jobName" -}}
{{- $ := index . 0 -}}
{{- $source := index . 1 -}}
{{ printf "%s-%s" $.Values.jobPrefix (include "flink-cdc-jobs.dnsName" $source.name) }}
{{- end -}}
