#!/usr/bin/env python3
"""
Loki gRPC Client
Loki log aggregation client
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from datetime import datetime
from .base_client import BaseGRPCClient
from .proto import loki_service_pb2, loki_service_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class LokiClient(BaseGRPCClient):
    """Loki gRPC Client"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 organization_id: Optional[str] = None, lazy_connect: bool = True,
                 enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        Initialize Loki client

        Args:
            host: Service host (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            organization_id: Organization ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'loki')
        """
        super().__init__(
            host=host,
            port=port,
            user_id=user_id,
            lazy_connect=lazy_connect,
            enable_compression=enable_compression,
            enable_retry=enable_retry,
            consul_registry=consul_registry,
            service_name_override=service_name_override
        )
        self.organization_id = organization_id or 'default-org'

    def _create_stub(self):
        """Create Loki service stub"""
        return loki_service_pb2_grpc.LokiServiceStub(self.channel)

    def service_name(self) -> str:
        return "Loki"

    def default_port(self) -> int:
        return 50054

    def health_check(self) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.LokiHealthCheckRequest(
                deep_check=False
            )
            response = self.stub.HealthCheck(request)

            print(f"✅ [Loki] Service healthy: {response.healthy}")
            print(f"   Loki status: {response.loki_status}")
            print(f"   Can write: {response.can_write}, Can read: {response.can_read}")

            return {
                'healthy': response.healthy,
                'loki_status': response.loki_status,
                'can_write': response.can_write,
                'can_read': response.can_read
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    def push_log(self, message: str, labels: Dict[str, str] = None,
                 timestamp: Optional[datetime] = None) -> Optional[Dict]:
        """Push single log entry"""
        try:
            self._ensure_connected()

            # Prepare timestamp
            ts = Timestamp()
            if timestamp:
                ts.FromDatetime(timestamp)
            else:
                ts.GetCurrentTime()

            # Prepare labels
            log_labels = labels or {}

            # Create log entry
            entry = loki_service_pb2.LogEntry(
                timestamp=ts,
                line=message,
                labels=log_labels
            )

            request = loki_service_pb2.PushLogRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                entry=entry
            )

            response = self.stub.PushLog(request)

            if response.success:
                print(f"✅ [Loki] Log pushed successfully")
                return {'success': True}
            else:
                print(f"⚠️  [Loki] Log push failed")
                return None

        except Exception as e:
            return self.handle_error(e, "Push log")

    def push_simple_log(self, message: str, service: str, level: str = 'INFO',
                       extra_labels: Dict[str, str] = None,
                       timestamp: Optional[datetime] = None) -> Optional[Dict]:
        """Push simple log (auto-add common labels)"""
        try:
            self._ensure_connected()

            # Prepare timestamp
            ts = Timestamp()
            if timestamp:
                ts.FromDatetime(timestamp)
            else:
                ts.GetCurrentTime()

            # Map log level
            level_map = {
                'DEBUG': loki_service_pb2.LOG_LEVEL_DEBUG,
                'INFO': loki_service_pb2.LOG_LEVEL_INFO,
                'WARNING': loki_service_pb2.LOG_LEVEL_WARN,
                'WARN': loki_service_pb2.LOG_LEVEL_WARN,
                'ERROR': loki_service_pb2.LOG_LEVEL_ERROR,
                'CRITICAL': loki_service_pb2.LOG_LEVEL_FATAL,
                'FATAL': loki_service_pb2.LOG_LEVEL_FATAL
            }
            log_level = level_map.get(level.upper(), loki_service_pb2.LOG_LEVEL_INFO)

            request = loki_service_pb2.PushSimpleLogRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                timestamp=ts,
                service=service,
                level=log_level,
                message=message,
                extra_labels=extra_labels or {}
            )

            response = self.stub.PushSimpleLog(request)

            if response.success:
                print(f"✅ [Loki] Log pushed: [{level}] {message[:50]}...")
                return {'success': True}
            else:
                print(f"⚠️  [Loki] Log push failed")
                return None

        except Exception as e:
            return self.handle_error(e, "Push simple log")

    def push_log_batch(self, entries: List[Dict]) -> Optional[Dict]:
        """Push batch logs"""
        try:
            self._ensure_connected()

            log_entries = []
            for entry in entries:
                ts = Timestamp()
                if 'timestamp' in entry and entry['timestamp']:
                    ts.FromDatetime(entry['timestamp'])
                else:
                    ts.GetCurrentTime()

                log_entry = loki_service_pb2.LogEntry(
                    timestamp=ts,
                    line=entry.get('message', ''),
                    labels=entry.get('labels', {})
                )
                log_entries.append(log_entry)

            request = loki_service_pb2.PushLogBatchRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                entries=log_entries
            )

            response = self.stub.PushLogBatch(request)

            print(f"✅ [Loki] Batch push completed: {response.accepted_count} accepted, {response.rejected_count} rejected")

            return {
                'success': response.success,
                'accepted_count': response.accepted_count,
                'rejected_count': response.rejected_count,
                'errors': list(response.errors) if response.errors else []
            }

        except Exception as e:
            return self.handle_error(e, "Push log batch")

    def query_logs(self, query: str, limit: int = 100,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None) -> List[Dict]:
        """Query logs"""
        try:
            self._ensure_connected()

            # Prepare time range
            start_ts = Timestamp()
            end_ts = Timestamp()

            if start_time:
                start_ts.FromDatetime(start_time)
            if end_time:
                end_ts.FromDatetime(end_time)
            else:
                end_ts.GetCurrentTime()

            request = loki_service_pb2.QueryLogsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                query=query,
                limit=limit,
                start=start_ts if start_time else None,
                end=end_ts
            )

            response = self.stub.QueryLogs(request)

            logs = []
            for entry in response.entries:
                logs.append({
                    'timestamp': entry.timestamp.ToDatetime(),
                    'message': entry.line,
                    'labels': dict(entry.labels)
                })

            print(f"✅ [Loki] Found {len(logs)} logs (total: {response.total_count})")
            return logs

        except Exception as e:
            return self.handle_error(e, "Query logs") or []

    def get_labels(self) -> List[str]:
        """Get available labels"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.GetLabelsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.GetLabels(request)

            print(f"✅ [Loki] Found {len(response.labels)} labels")
            return list(response.labels)

        except Exception as e:
            return self.handle_error(e, "Get labels") or []

    def get_label_values(self, label: str) -> List[str]:
        """Get values for specific label"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.GetLabelValuesRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                label_name=label
            )

            response = self.stub.GetLabelValues(request)

            print(f"✅ [Loki] Label '{label}' has {len(response.values)} values")
            return list(response.values)

        except Exception as e:
            return self.handle_error(e, f"Get label values ({label})") or []

    def push_log_stream(self, log_generator):
        """
        Push logs via streaming (high throughput)
        
        Args:
            log_generator: Generator yielding dicts with 'message', 'labels', 'timestamp'
        """
        try:
            self._ensure_connected()
            
            def request_generator():
                for log_data in log_generator:
                    ts = Timestamp()
                    if 'timestamp' in log_data and log_data['timestamp']:
                        ts.FromDatetime(log_data['timestamp'])
                    else:
                        ts.GetCurrentTime()
                    
                    entry = loki_service_pb2.LogEntry(
                        timestamp=ts,
                        line=log_data.get('message', ''),
                        labels=log_data.get('labels', {})
                    )
                    
                    yield loki_service_pb2.PushLogRequest(
                        user_id=self.user_id,
                        organization_id=self.organization_id,
                        entry=entry
                    )
            
            response = self.stub.PushLogStream(request_generator())
            
            print(f"✅ [Loki] Stream push completed: {response.accepted_count} accepted, {response.rejected_count} rejected")
            
            return {
                'success': response.success,
                'accepted_count': response.accepted_count,
                'rejected_count': response.rejected_count
            }

        except Exception as e:
            return self.handle_error(e, "Push log stream")

    def query_range(self, query: str, start_time: datetime, end_time: datetime,
                    step: int = 60, limit: int = 1000) -> Optional[Dict]:
        """
        Range query with time series aggregation
        
        Args:
            query: LogQL query
            start_time: Start time
            end_time: End time
            step: Step size in seconds
            limit: Max results
        """
        try:
            self._ensure_connected()
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(end_time)
            
            request = loki_service_pb2.QueryRangeRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                query=query,
                start=start_ts,
                end=end_ts,
                step=step,
                limit=limit
            )

            response = self.stub.QueryRange(request)

            results = {
                'result_type': response.result_type,
                'matrix_results': [],
                'stream_results': [],
                'stats': dict(response.stats)
            }
            
            # Parse matrix results
            for matrix in response.matrix_results:
                results['matrix_results'].append({
                    'metric': dict(matrix.metric),
                    'values': [(p.timestamp, p.value) for p in matrix.values]
                })
            
            # Parse stream results
            for stream in response.stream_results:
                results['stream_results'].append({
                    'stream': dict(stream.stream),
                    'entries': [{
                        'timestamp': e.timestamp,
                        'line': e.line,
                        'labels': dict(e.labels)
                    } for e in stream.entries]
                })
            
            print(f"✅ [Loki] Range query completed: {len(results['stream_results'])} streams")
            return results

        except Exception as e:
            return self.handle_error(e, "Query range")

    def tail_logs(self, query: str, callback=None, limit: int = 100, delay_for: int = 0):
        """
        Tail logs in real-time (like tail -f)
        
        Args:
            query: LogQL query
            callback: Function to call for each log entry
            limit: Max entries to tail
            delay_for: Delay seconds before starting
        """
        try:
            self._ensure_connected()
            
            start_ts = None
            if delay_for > 0:
                start_ts = Timestamp()
                start_ts.GetCurrentTime()
            
            request = loki_service_pb2.TailLogsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                query=query,
                limit=limit,
                delay_for=delay_for,
                start=start_ts
            )

            print(f"✅ [Loki] Tailing logs: {query}")
            
            for entry in self.stub.TailLogs(request):
                if callback:
                    callback(entry.timestamp, entry.line, dict(entry.labels))
                else:
                    print(f"📝 [{entry.timestamp}] {entry.line}")

        except Exception as e:
            self.handle_error(e, "Tail logs")

    def query_stats(self, query: str, start_time: datetime, end_time: datetime) -> Optional[Dict]:
        """Get query statistics"""
        try:
            self._ensure_connected()
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(end_time)
            
            request = loki_service_pb2.QueryStatsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                query=query,
                start=start_ts,
                end=end_ts
            )

            response = self.stub.QueryStats(request)

            stats = {
                'total_entries': response.total_entries,
                'total_bytes': response.total_bytes,
                'streams_count': response.streams_count,
                'query_time_ms': response.query_time_ms,
                'level_distribution': dict(response.level_distribution),
                'top_labels': list(response.top_labels)
            }
            
            print(f"✅ [Loki] Query stats: {response.total_entries} entries, {response.streams_count} streams")
            print(f"   Query time: {response.query_time_ms:.2f}ms")
            return stats

        except Exception as e:
            return self.handle_error(e, "Query stats")

    def validate_labels(self, labels: Dict[str, str]) -> Optional[Dict]:
        """Validate labels format"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.ValidateLabelsRequest(
                labels=labels
            )

            response = self.stub.ValidateLabels(request)

            if response.valid:
                print(f"✅ [Loki] Labels valid")
            else:
                print(f"⚠️  [Loki] Labels invalid: {response.message}")
                print(f"   Violations: {', '.join(response.violations)}")
            
            return {
                'valid': response.valid,
                'violations': list(response.violations),
                'message': response.message
            }

        except Exception as e:
            return self.handle_error(e, "Validate labels")

    def list_streams(self, label_filter: Dict[str, str] = None, page: int = 1, 
                     page_size: int = 50) -> Optional[Dict]:
        """List log streams"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.ListStreamsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                label_filter=label_filter or {},
                page=page,
                page_size=page_size
            )

            response = self.stub.ListStreams(request)

            streams = []
            for stream in response.streams:
                streams.append({
                    'stream_id': stream.stream_id,
                    'labels': dict(stream.labels),
                    'entry_count': stream.entry_count,
                    'bytes': stream.bytes,
                    'first_entry_at': stream.first_entry_at,
                    'last_entry_at': stream.last_entry_at
                })
            
            print(f"✅ [Loki] Listed {len(streams)} streams (total: {response.total_count})")
            return {
                'streams': streams,
                'total_count': response.total_count,
                'page': response.page,
                'page_size': response.page_size
            }

        except Exception as e:
            return self.handle_error(e, "List streams")

    def get_stream_info(self, stream_id: str) -> Optional[Dict]:
        """Get stream information"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.GetStreamInfoRequest(
                user_id=self.user_id,
                stream_id=stream_id
            )

            response = self.stub.GetStreamInfo(request)

            stream = response.stream
            info = {
                'stream_id': stream.stream_id,
                'labels': dict(stream.labels),
                'entry_count': stream.entry_count,
                'bytes': stream.bytes,
                'first_entry_at': stream.first_entry_at,
                'last_entry_at': stream.last_entry_at,
                'user_id': stream.user_id,
                'organization_id': stream.organization_id
            }
            
            print(f"✅ [Loki] Stream info: {stream_id}")
            print(f"   Entries: {stream.entry_count}, Bytes: {stream.bytes}")
            return info

        except Exception as e:
            return self.handle_error(e, "Get stream info")

    def delete_stream(self, stream_id: str, start_time: datetime = None, 
                     end_time: datetime = None) -> Optional[Dict]:
        """Delete log stream"""
        try:
            self._ensure_connected()
            
            start_ts = None
            end_ts = None
            if start_time:
                start_ts = Timestamp()
                start_ts.FromDatetime(start_time)
            if end_time:
                end_ts = Timestamp()
                end_ts.FromDatetime(end_time)
            
            request = loki_service_pb2.DeleteStreamRequest(
                user_id=self.user_id,
                stream_id=stream_id,
                start=start_ts,
                end=end_ts
            )

            response = self.stub.DeleteStream(request)

            if response.success:
                print(f"✅ [Loki] Stream deleted: {stream_id}")
                print(f"   Deleted {response.deleted_entries} entries")
                return {
                    'success': True,
                    'deleted_entries': response.deleted_entries,
                    'message': response.message
                }
            else:
                print(f"⚠️  [Loki] Stream deletion failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "Delete stream")

    def export_logs(self, query: str, start_time: datetime, end_time: datetime,
                    format: str = 'JSONL', chunk_size: int = 1000, callback=None):
        """
        Export logs to file (streaming)
        
        Args:
            query: LogQL query
            start_time: Start time
            end_time: End time
            format: Export format (JSON, JSONL, CSV, TEXT)
            chunk_size: Chunk size
            callback: Function to call for each chunk
        """
        try:
            self._ensure_connected()
            
            start_ts = Timestamp()
            start_ts.FromDatetime(start_time)
            end_ts = Timestamp()
            end_ts.FromDatetime(end_time)
            
            # Map format string to enum
            format_map = {
                'JSON': 0,
                'JSONL': 1,
                'CSV': 2,
                'TEXT': 3
            }
            export_format = format_map.get(format.upper(), 1)
            
            request = loki_service_pb2.ExportLogsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                query=query,
                start=start_ts,
                end=end_ts,
                format=export_format,
                chunk_size=chunk_size
            )

            print(f"✅ [Loki] Exporting logs...")
            
            for response in self.stub.ExportLogs(request):
                if callback:
                    callback(response.export_id, response.data, response.processed_entries,
                            response.total_entries, response.complete)
                else:
                    print(f"   📦 Chunk: {response.processed_entries}/{response.total_entries} entries")
                
                if response.complete:
                    print(f"   ✅ Export complete: {response.export_id}")
                    break

        except Exception as e:
            self.handle_error(e, "Export logs")

    def get_export_status(self, export_id: str) -> Optional[Dict]:
        """Get export task status"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.GetExportStatusRequest(
                user_id=self.user_id,
                export_id=export_id
            )

            response = self.stub.GetExportStatus(request)

            status = {
                'export_id': response.export_id,
                'status': response.status,
                'total_entries': response.total_entries,
                'exported_entries': response.exported_entries,
                'progress_percentage': response.progress_percentage,
                'created_at': response.created_at,
                'completed_at': response.completed_at,
                'error_message': response.error_message
            }
            
            print(f"✅ [Loki] Export status: {response.status} ({response.progress_percentage}%)")
            return status

        except Exception as e:
            return self.handle_error(e, "Get export status")

    def get_statistics(self, start_time: datetime = None, end_time: datetime = None) -> Optional[Dict]:
        """Get Loki statistics"""
        try:
            self._ensure_connected()
            
            start_ts = None
            end_ts = None
            if start_time:
                start_ts = Timestamp()
                start_ts.FromDatetime(start_time)
            if end_time:
                end_ts = Timestamp()
                end_ts.FromDatetime(end_time)
            
            request = loki_service_pb2.GetStatisticsRequest(
                user_id=self.user_id,
                organization_id=self.organization_id,
                start=start_ts,
                end=end_ts
            )

            response = self.stub.GetStatistics(request)

            stats = {
                'total_entries': response.total_entries,
                'total_bytes': response.total_bytes,
                'streams_count': response.streams_count,
                'entries_by_service': dict(response.entries_by_service),
                'entries_by_level': dict(response.entries_by_level),
                'ingestion_rate': [(p.timestamp, p.value) for p in response.ingestion_rate],
                'top_services': list(response.top_services),
                'metadata': dict(response.metadata)
            }
            
            print(f"✅ [Loki] Statistics retrieved:")
            print(f"   Total entries: {response.total_entries}")
            print(f"   Total bytes: {response.total_bytes/1024/1024:.2f}MB")
            print(f"   Streams: {response.streams_count}")
            return stats

        except Exception as e:
            return self.handle_error(e, "Get statistics")

    def get_user_quota(self) -> Optional[Dict]:
        """Get user quota information"""
        try:
            self._ensure_connected()
            request = loki_service_pb2.GetUserQuotaRequest(
                user_id=self.user_id,
                organization_id=self.organization_id
            )

            response = self.stub.GetUserQuota(request)

            print(f"✅ [Loki] Quota: today used {response.today_used}/{response.daily_limit}")
            print(f"   Storage: {response.storage_used_bytes / 1024 / 1024:.2f}MB / {response.storage_limit_bytes / 1024 / 1024:.2f}MB")
            print(f"   Retention: {response.retention_days} days")

            return {
                'daily_limit': response.daily_limit,
                'today_used': response.today_used,
                'storage_limit_bytes': response.storage_limit_bytes,
                'storage_used_bytes': response.storage_used_bytes,
                'retention_days': response.retention_days,
                'quota_exceeded': response.quota_exceeded
            }

        except Exception as e:
            return self.handle_error(e, "Get user quota")


# Convenience usage example
if __name__ == '__main__':
    with LokiClient(host='localhost', port=50054, user_id='test_user') as client:
        # Health check
        client.health_check()

        # Push simple log
        client.push_simple_log(
            message="Application started successfully",
            service="my-service",
            level="INFO"
        )

        # Push log with labels
        client.push_log(
            message="User login successful",
            labels={
                "action": "login",
                "user": "john_doe",
                "ip": "192.168.1.1"
            }
        )

        # Batch push
        logs = [
            {"message": "Processing request 1", "labels": {"request_id": "req-1"}},
            {"message": "Processing request 2", "labels": {"request_id": "req-2"}},
            {"message": "Processing request 3", "labels": {"request_id": "req-3"}}
        ]
        client.push_log_batch(logs)

        # Query logs
        results = client.query_logs(query='{service="my-service"}', limit=10)
        print(f"Query results: {results}")

        # Get quota info
        quota = client.get_user_quota()
        print(f"Quota info: {quota}")
