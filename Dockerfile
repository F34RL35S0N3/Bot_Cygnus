FROM python:3.11-slim
 
WORKDIR /app
 
# Install Node.js (untuk generate .docx)
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
RUN npm install -g docx
 
# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy SEMUA file Python
COPY bot.py .
COPY feature_lomba.py .
 
CMD ["python", "bot.py"]
 
