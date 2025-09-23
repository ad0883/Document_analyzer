#!/bin/bash

# Download NLTK data if not already present
python -c "
import nltk
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/words')
except LookupError:
    nltk.download('words')
"

# Start the application with gunicorn
exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120 advanced_analyzer:app
