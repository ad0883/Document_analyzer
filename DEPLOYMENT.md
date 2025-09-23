# Document Analyzer - Render Deployment

## Deployment Instructions

### Method 1: Using Render Dashboard (Recommended)

1. **Push your code to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for Render deployment"
   git branch -M main
   git remote add origin https://github.com/yourusername/document-analyzer.git
   git push -u origin main
   ```

2. **Deploy on Render**:
   - Go to [render.com](https://render.com) and sign up/login
   - Click "New +" and select "Web Service"
   - Connect your GitHub repository
   - Use these settings:
     - **Environment**: Docker
     - **Dockerfile Path**: `./Dockerfile`
     - **Instance Type**: Free tier or Starter ($7/month)

### Method 2: Using render.yaml (Infrastructure as Code)

1. Push your code to GitHub (same as above)
2. In Render dashboard, select "New +" → "Blueprint"
3. Connect your repository
4. Render will automatically detect the `render.yaml` file

### Method 3: Manual Docker Deployment

For local testing:
```bash
# Build the Docker image
docker build -t document-analyzer .

# Run the container
docker run -p 8080:8080 -e FLASK_ENV=production document-analyzer
```

## Environment Variables

The following environment variables are used:
- `PORT`: Port number (default: 8080)
- `FLASK_ENV`: Environment mode (production/development)

## Features

- ✅ Advanced spell checking with pattern recognition
- ✅ Email validation and format checking
- ✅ Typography and formatting analysis
- ✅ Document structure analysis
- ✅ Support for PDF, DOCX, and TXT files
- ✅ Grammar checking (when LanguageTool is available)
- ✅ Production-ready with Gunicorn
- ✅ Containerized with Docker

## Start Command

The application uses gunicorn for production deployment:
```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 advanced_analyzer:app
```

## Notes

- The application includes Java runtime for LanguageTool grammar checking
- NLTK data is automatically downloaded during container build
- Maximum file size is limited to 50MB
- Single worker configuration to manage memory usage effectively
