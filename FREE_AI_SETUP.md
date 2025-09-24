# 🆓 Free AI Provider Setup Guide

Your document analyzer now supports **3 FREE AI providers**! Choose any one:

## 🥇 **Google Gemini (RECOMMENDED - Best Free Option)**

### Why Choose Gemini?
- ✅ **Completely FREE** - 15 requests/minute, 1M tokens/day
- ✅ **No credit card required**
- ✅ **High quality results**
- ✅ **Easy setup**

### Setup Steps:
1. **Get Free API Key:**
   - Go to: https://aistudio.google.com/app/apikey
   - Sign in with Google account
   - Click "Create API Key"
   - Copy the key (starts with `AIzaSy...`)

2. **Add to .env file:**
   ```bash
   GEMINI_API_KEY=AIzaSy...your_actual_key_here
   ```

---

## 🥈 **Hugging Face (Alternative Free Option)**

### Why Choose Hugging Face?
- ✅ **FREE** - 1000 requests/month
- ✅ **No credit card required**
- ✅ **Open source models**

### Setup Steps:
1. **Get Free Token:**
   - Go to: https://huggingface.co/settings/tokens
   - Sign up/login
   - Click "New token"
   - Copy the token (starts with `hf_...`)

2. **Add to .env file:**
   ```bash
   HUGGINGFACE_API_KEY=hf_...your_actual_token_here
   ```

---

## 🥉 **OpenAI (Paid but Most Accurate)**

### Why Choose OpenAI?
- ✅ **Most accurate results**
- ❌ **Requires credit card**
- ❌ **Costs money** (~$0.002 per 1K tokens)

### Setup Steps:
1. **Get API Key:**
   - Go to: https://platform.openai.com/api-keys
   - Add credit card for billing
   - Create API key

2. **Add to .env file:**
   ```bash
   OPENAI_API_KEY=sk-proj-...your_actual_key_here
   ```

---

## 🚀 **Quick Start (Recommended: Gemini)**

1. **Get Gemini API Key** (free, no card needed):
   ```
   https://aistudio.google.com/app/apikey
   ```

2. **Create/edit .env file:**
   ```bash
   echo "GEMINI_API_KEY=AIzaSy...your_key_here" > .env
   ```

3. **Restart the application:**
   ```bash
   # Stop current app (Ctrl+C)
   source venv/bin/activate
   python advanced_analyzer.py
   ```

4. **Look for this message:**
   ```
   ✅ AI-powered error detection enabled (Google Gemini - Free)
   ```

---

## 🔧 **Priority System**

The system automatically uses the **first available** API key in this order:

1. **OpenAI** (if `OPENAI_API_KEY` exists)
2. **Gemini** (if `GEMINI_API_KEY` exists)  ← **RECOMMENDED**
3. **Hugging Face** (if `HUGGINGFACE_API_KEY` exists)
4. **Local Analysis** (fallback - still very good!)

---

## 🎯 **Results Comparison**

| Provider | Cost | Rate Limit | Quality | Setup |
|----------|------|------------|---------|--------|
| **Gemini** | 🆓 FREE | 15/min | ⭐⭐⭐⭐⭐ | Easy |
| Hugging Face | 🆓 FREE | 1000/month | ⭐⭐⭐⭐ | Easy |
| OpenAI | 💰 Paid | High | ⭐⭐⭐⭐⭐ | Easy |
| Local | 🆓 FREE | No limit | ⭐⭐⭐ | No setup |

---

## 🛠 **Troubleshooting**

**Q: Which should I choose?**
A: **Google Gemini** - it's free, fast, and high-quality!

**Q: I'm getting rate limit errors**
A: Switch to Gemini (15 requests/minute vs OpenAI's 3/minute free tier)

**Q: Do I need a credit card?**
A: NO for Gemini and Hugging Face. YES for OpenAI.

**Q: Can I use multiple providers?**
A: Yes! The system will use the first available key automatically.

---

**🎉 Your document analyzer now has powerful AI capabilities for FREE!**
