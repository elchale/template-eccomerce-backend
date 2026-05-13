# Google Cloud Services custom settings

from .env import env

GCS_BUCKET_NAME = env('GCS_BUCKET_NAME', default='')
GCS_PROJECT_ID = env('GCS_PROJECT_ID', default='')

# Production (Railway, Render, etc.): base64-encoded service account JSON.
# Generate with: base64 -w 0 your-key.json  (Linux/Mac)
#   or: [Convert]::ToBase64String([IO.File]::ReadAllBytes("your-key.json"))  (PowerShell)
# Set as GCS_CREDENTIALS_JSON env var in Railway dashboard — never commit the raw JSON.
GCS_CREDENTIALS_JSON = env('GCS_CREDENTIALS_JSON', default='')

# Local development only: path to the service account JSON file on disk.
GCS_CREDENTIALS_PATH = env('GCS_CREDENTIALS_PATH', default='')
