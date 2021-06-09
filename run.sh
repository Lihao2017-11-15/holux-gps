cd /home/pi/backend
python -m uvicorn server:app &
python -m http.server --directory html 8080 &
chromium-browser http://localhost:8080 -kiosk --incognito --noerrdialogs
