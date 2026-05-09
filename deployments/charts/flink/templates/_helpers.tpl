{{/*
Common labels.
*/}}
{{- define "flink.labels" -}}
app: {{ .Values.name }}
app.kubernetes.io/name: flink
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: isa-bigdata
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Selector labels — stable subset for pod selection. Must match what the
Flink operator emits on JM + TM pods (it derives from FlinkDeployment.metadata.name).
*/}}
{{- define "flink.sessionSelector" -}}
app: {{ .Values.session.name }}
{{- end -}}
