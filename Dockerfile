# 1. Use Microsoft's official Playwright Python image as the foundation.
# This comes pre-packaged with all the Linux OS graphics libraries 
# required to run headless Chromium without throwing errors.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# 2. Establish the internal working directory
WORKDIR /app

# 3. Layer Caching: Copy requirements first so Docker skips re-installing 
# your packages every time you make a tiny code change.
COPY requirements.txt .

# 4. Install dependencies cleanly without saving temporary cache files
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your application code into the container
COPY . .

# 6. Document that the container intends to use port 10000
EXPOSE 10000

# 7. Start Uvicorn using the dynamic PORT variable provided by Render
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]