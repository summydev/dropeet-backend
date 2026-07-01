# 1. Start with a clean, lightweight, standard Python image
FROM python:3.10-slim

# 2. Establish the internal working directory
WORKDIR /app

# 3. Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Force Playwright to download the exact matching browser locally
RUN playwright install chromium

# 5. Crucial Step: Tell Playwright to download all the missing Linux 
# graphics libraries (like libgbm1, libxss1) that the browser needs to run
RUN playwright install-deps chromium

# 6. Copy the rest of your application code
COPY . .

# 7. Document the port
EXPOSE 10000

# 8. Start Uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]