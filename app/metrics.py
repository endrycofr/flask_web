from prometheus_client import Counter, Histogram

# Metrik untuk menghitung jumlah permintaan HTTP
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint'])

# Metrik untuk menghitung durasi permintaan (latency)
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'Request duration histogram', ['method', 'endpoint'])

# Metrik untuk mengukur response time
RESPONSE_TIME = Histogram('http_response_time_seconds', 'HTTP Response time', ['method', 'endpoint'])

# Metrik untuk throughput (permintaan per detik)
THROUGHPUT = Counter('http_throughput_total', 'Total HTTP Throughput in requests/sec', ['method', 'endpoint'])

# Metrik untuk delay (waktu tunda antara permintaan dan respon)
REQUEST_DELAY = Histogram('http_request_delay_seconds', 'Request delay time in seconds', ['method', 'endpoint'])
