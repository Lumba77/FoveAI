pkill -f "theme_api.py" || true
sleep 1
nohup /home/lumba/FoveAI/.venv/bin/python /home/lumba/FoveAI/theme/theme_api.py > /tmp/theme_api.log 2>&1 &
echo "Restarted API with WebSockets!"
