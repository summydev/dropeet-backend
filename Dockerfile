# 1. Start with a clean, lightweight, standard Python image
FROM python:3.10-slim

# 2. Establish the internal working directory
WORKDIR /app

# 3. Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. THE MAGIC LINE: Force Playwright to save the browser locally 
# where the restricted Render user has full permission to read it
ENV PLAYWRIGHT_BROWSERS_PATH=0

# 5. Download the local browser and Linux graphics libraries
RUN playwright install chromium
RUN playwright install-deps chromium

# 6. Copy the rest of your application code
COPY . .

# 7. Document the port
EXPOSE 10000

# 8. Start Uvicorn
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]