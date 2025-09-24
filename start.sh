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
#!/bin/bash

# Production startup script for Document Analyzer
echo "🚀 Starting Document Analyzer..."

# Download NLTK data if not present
echo "📚 Ensuring NLTK data is available..."
python -c "
import nltk
try:
    nltk.data.find('tokenizers/punkt')
    print('✅ NLTK punkt data found')
except LookupError:
    print('📥 Downloading NLTK punkt data...')
    nltk.download('punkt')

try:
    nltk.data.find('corpora/words')
    print('✅ NLTK words data found')
except LookupError:
    print('📥 Downloading NLTK words data...')
    nltk.download('words')
"

# Check environment variables
echo "🔧 Checking configuration..."
if [ -n "$GEMINI_API_KEY" ]; then
    echo "✅ Gemini API key configured"
elif [ -n "$OPENAI_API_KEY" ]; then
    echo "✅ OpenAI API key configured"
else
    echo "⚠️  No AI API key found - using local analysis only"
fi

# Start the application with gunicorn
echo "🌐 Starting web server..."
exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120 --access-logfile - --error-logfile - advanced_analyzer:app
