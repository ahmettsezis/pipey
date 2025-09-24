# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
ENV TZ=Europe/Istanbul
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code to the working directory
COPY . .

EXPOSE 5000

# Define environment variable to turn off Flask's debug mode in production
ENV FLASK_DEBUG=0

# Run app.py when the container launches
# Use gunicorn for a production-ready server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
