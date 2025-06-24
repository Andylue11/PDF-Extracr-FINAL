# RFMS PDF Xtracr - Deployment Guide

## 🚀 Cloud Deployment Options

### Option 1: GitHub + Heroku (Recommended)

#### Step 1: Push to GitHub
```bash
# Add GitHub remote (replace with your repository URL)
git remote add origin https://github.com/yourusername/rfms-pdf-xtracr.git

# Commit and push
git add .
git commit -m "Initial commit: RFMS PDF Xtracr application"
git push -u origin master
```

#### Step 2: Deploy to Heroku
1. Create account at [heroku.com](https://heroku.com)
2. Install Heroku CLI
3. Deploy:
```bash
heroku create your-app-name
heroku config:set SECRET_KEY=your-secret-key
heroku config:set RFMS_STORE_CODE=your-store-code
heroku config:set RFMS_USERNAME=your-username
heroku config:set RFMS_API_KEY=your-api-key
heroku config:set RFMS_STORE_NUMBER=your-store-number
git push heroku master
```

### Option 2: Google Cloud Platform

#### Prerequisites
- Google Cloud account
- `gcloud` CLI installed

#### Deployment
```bash
# Create app.yaml
gcloud app deploy

# Set environment variables
gcloud app config set env-vars RFMS_STORE_CODE=your-code,...
```

### Option 3: AWS Elastic Beanstalk

#### Prerequisites
- AWS account
- EB CLI installed

#### Deployment
```bash
eb init
eb create production
eb deploy
```

### Option 4: Azure App Service

#### Prerequisites
- Azure account
- Azure CLI installed

#### Deployment
```bash
az webapp up --name your-app-name --resource-group your-rg
```

## 🔒 Security Considerations

1. **Environment Variables**: Never commit `.env` file
2. **Database**: Use cloud database for production
3. **File Storage**: Use cloud storage (AWS S3, Google Cloud Storage)
4. **HTTPS**: Always use SSL/TLS in production
5. **API Keys**: Rotate regularly

## 📦 Production Requirements

Create `requirements-prod.txt`:
```
gunicorn==21.2.0
psycopg2-binary==2.9.7  # For PostgreSQL
```

## 🔧 Production Configuration

Update `app.py` for production:
```python
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
```

## 📊 Monitoring & Logs

- Enable application logging
- Set up health checks
- Monitor API usage
- Track performance metrics

## 🔄 CI/CD Pipeline

Consider setting up automated deployment with:
- GitHub Actions
- GitLab CI/CD
- Azure DevOps
- AWS CodePipeline 