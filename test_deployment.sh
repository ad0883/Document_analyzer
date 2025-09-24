#!/bin/bash

# 🧪 Pre-Deployment Testing Script for Document Analyzer

echo "🚀 Document Analyzer - Pre-Deployment Testing"
echo "=============================================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found!"
    echo "📝 Please copy .env.example to .env and add your API keys"
    echo ""
    echo "cp .env.example .env"
    echo "# Then edit .env with your actual API keys"
    exit 1
fi

# Check for required environment variables
source .env 2>/dev/null || true

echo "🔧 Environment Check:"
if [ -n "$GEMINI_API_KEY" ]; then
    echo "✅ Gemini API key configured"
elif [ -n "$OPENAI_API_KEY" ]; then
    echo "✅ OpenAI API key configured"
elif [ -n "$HUGGINGFACE_API_KEY" ]; then
    echo "✅ Hugging Face API key configured"
else
    echo "⚠️  No AI API key found - will use local analysis only"
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "🔨 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Check if main files exist
echo ""
echo "📁 File Check:"
files=("advanced_analyzer.py" "premium_index.html" "version_selector.html" "Dockerfile" "render.yaml" "requirements.txt")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file exists"
    else
        echo "❌ $file missing!"
    fi
done

# Run quick syntax check
echo ""
echo "🔍 Syntax Check:"
python3 -m py_compile advanced_analyzer.py && echo "✅ Python syntax OK" || echo "❌ Python syntax errors"

# Test local server startup
echo ""
echo "🌐 Testing local server startup..."
export FLASK_ENV=development
export PORT=5000

# Start server in background and test
python3 advanced_analyzer.py &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Test if server is responding
if curl -s http://localhost:5000/ > /dev/null; then
    echo "✅ Server started successfully!"
    echo "🌍 Local server running at: http://localhost:5000"
    echo "🎯 Premium interface at: http://localhost:5000/premium"
else
    echo "❌ Server failed to start"
fi

# Clean up
kill $SERVER_PID 2>/dev/null

echo ""
echo "🎉 Pre-deployment testing complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Fix any issues shown above"
echo "2. Test the local server manually"
echo "3. Commit and push to GitHub"
echo "4. Deploy to Render following DEPLOYMENT.md"
echo ""
echo "🚀 Ready to deploy? Check DEPLOYMENT.md for full instructions!"

deactivate
