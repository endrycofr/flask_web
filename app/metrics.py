from prometheus_client import Counter, Histogram, Gauge
from flask import request
import time


# HTTP Requests Metrics
HTTP_REQUESTS = Counter(
    'http_requests_total', 
    'Total number of HTTP requests', 
    ['method', 'endpoint', 'http_status']
)

HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration_seconds', 
    'Duration of HTTP requests in seconds', 
    ['method', 'endpoint']
)

IN_PROGRESS_REQUESTS = Gauge(
    'http_requests_in_progress', 
    'Number of HTTP requests currently in progress',
    ['method', 'endpoint']
)

# Exceptions Metrics
EXCEPTIONS = Counter(
    'exceptions_total',
    'Total number of exceptions',
    ['method', 'endpoint', 'exception_type']
)

# Database Operations Metrics
DATABASE_OPERATIONS = Counter(
    'database_operations_total',
    'Total number of database operations',
    ['operation_type', 'status']
)

# Events Processed Metrics
EVENTS_PROCESSED = Counter(
    'events_processed', 
    'Total number of events processed', 
    ['type', 'status']
)

EVENT_PROCESSING_DURATION = Histogram(
    'event_processing_duration_seconds', 
    'Duration of event processing in seconds', 
    ['type']
)

def record_request_start(method, endpoint):
    """Record the start of a request"""
    IN_PROGRESS_REQUESTS.labels(method=method, endpoint=endpoint).inc()
    return time.time()

def record_request_end(method, endpoint, start_time, status_code):
    """Record the end of a request"""
    duration = time.time() - start_time
    
    # Record request duration
    HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
    
    # Record total requests
    HTTP_REQUESTS.labels(method=method, endpoint=endpoint, http_status=status_code).inc()
    
    # Decrement in-progress requests
    IN_PROGRESS_REQUESTS.labels(method=method, endpoint=endpoint).dec()

def record_event_processing(event_type, status, duration):
    """Record event processing metrics"""
    EVENTS_PROCESSED.labels(type=event_type, status=status).inc()
    EVENT_PROCESSING_DURATION.labels(type=event_type).observe(duration)

def record_exception(method, endpoint, exception_type):
    """Record exception metrics"""
    EXCEPTIONS.labels(
        method=method, 
        endpoint=endpoint, 
        exception_type=exception_type
    ).inc()

def record_database_operation(operation_type, status):
    """Record database operation metrics"""
    DATABASE_OPERATIONS.labels(
        operation_type=operation_type, 
        status=status
    ).inc()