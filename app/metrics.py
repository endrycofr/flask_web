import prometheus_client
from prometheus_flask_exporter import PrometheusMetrics

# Define custom metrics
ACTIVE_REQUESTS = prometheus_client.Gauge(
    'active_requests_total', 
    'Number of active requests currently being processed'
)

COMPLETED_REQUESTS = prometheus_client.Counter(
    'completed_requests_total', 
    'Total number of completed requests'
)

REQUEST_DURATION = prometheus_client.Histogram(
    'request_duration_seconds', 
    'Request duration in seconds',
    buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)

EXCEPTIONS = prometheus_client.Counter(
    'exceptions_total', 
    'Total number of exceptions',
    ['method', 'endpoint', 'exception_type']
)

HTTP_REQUESTS = prometheus_client.Counter(
    'http_requests_total', 
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

DATABASE_OPERATIONS = prometheus_client.Counter(
    'database_operations_total', 
    'Total database operations',
    ['operation_type', 'status']
)

REQUEST_SIZE = prometheus_client.Histogram(
    'request_size_bytes', 
    'Request size in bytes',
    buckets=[100, 500, 1000, 2500, 5000, 10000]
)

RESPONSE_SIZE = prometheus_client.Histogram(
    'response_size_bytes', 
    'Response size in bytes',
    buckets=[100, 500, 1000, 2500, 5000, 10000]
)