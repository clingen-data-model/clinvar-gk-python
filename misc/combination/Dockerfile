# Use a smaller base image
FROM python:3.9-slim AS build
WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final image
FROM python:3.9-slim
WORKDIR /app

# Copy dependencies from the build stage
COPY --from=build /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/

# Copy the application code
COPY combine-files.py .

# Set environment variables if needed
ENV PYTHONUNBUFFERED=1

# Command to run the Flask app
CMD ["python","combine-files.py"]
