{{- define "ingestion-worker.fullname" -}}
ingestion-worker
{{- end }}

{{- define "ingestion-worker.labels" -}}
app.kubernetes.io/name: ingestion-worker
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ingestion-worker.selectorLabels" -}}
app.kubernetes.io/name: ingestion-worker
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
