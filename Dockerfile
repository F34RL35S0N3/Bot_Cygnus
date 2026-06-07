FROM python:3.11-slim
 
WORKDIR /app
 
# Install Node.js (untuk generate .docx)
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*
RUN mkdir /app/node_modules
WORKDIR /app
RUN npm init -y
RUN npm install docx
 
# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy SEMUA file Python
COPY bot.py .
COPY feature_lomba.py .
 
CMD ["python", "bot.py"]
 
