PORT=8000

# Build
docker build -t gdrive-copilot-backend .

# Run
docker run -d -p 0.0.0.0:8000:$PORT -e "PORT=$PORT" gdrive-copilot-backend