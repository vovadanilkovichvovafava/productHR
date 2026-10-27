"""
Application constants - centralized configuration values.
Replaces magic numbers throughout the codebase.
"""

# File upload limits
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Search limits
SEARCH_QUERY_MAX_LENGTH = 100
SEARCH_RESULTS_DEFAULT_LIMIT = 5
SEARCH_RESULTS_MAX_LIMIT = 20

# Pagination defaults
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# AI/LLM limits
AI_MAX_CONTEXT_TOKENS = 4000
AI_MAX_RESPONSE_TOKENS = 2000

# Rate limiting
RATE_LIMIT_REQUESTS_PER_MINUTE = 60
RATE_LIMIT_REQUESTS_PER_HOUR = 1000

# Session/Auth
SESSION_EXPIRE_HOURS = 24
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

# WebSocket
WEBSOCKET_PING_INTERVAL_SECONDS = 30
WEBSOCKET_TIMEOUT_SECONDS = 60

# Database
DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 10
DB_POOL_TIMEOUT = 30

# Cache TTL (seconds)
CACHE_TTL_SHORT = 60  # 1 minute
CACHE_TTL_MEDIUM = 300  # 5 minutes
CACHE_TTL_LONG = 3600  # 1 hour

# Allowed file extensions for upload
ALLOWED_DOCUMENT_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.ppt', '.pptx', '.txt', '.rtf', '.csv'
}

ALLOWED_IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic'
}

ALLOWED_ARCHIVE_EXTENSIONS = {
    '.zip', '.rar', '.7z', '.tar', '.gz'
}

# MIME type mappings for magic bytes validation
MIME_TYPE_EXTENSIONS = {
    'application/pdf': ['.pdf'],
    'application/msword': ['.doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'application/vnd.ms-excel': ['.xls'],
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    'application/vnd.ms-powerpoint': ['.ppt'],
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
    'text/plain': ['.txt'],
    'text/csv': ['.csv'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/gif': ['.gif'],
    'image/webp': ['.webp'],
}
