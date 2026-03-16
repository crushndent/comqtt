from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import requests
from django.conf import settings

COMQTT_API_URL = "http://localhost:8080/api/v1/mqtt"

@login_required
def dashboard(request):
    try:
        # Fetch Overall Stats
        overall_resp = requests.get(f"{COMQTT_API_URL}/stat/overall", timeout=2)
        overall_stats = overall_resp.json() if overall_resp.status_code == 200 else {}

        # Fetch Config (optional)
        config_resp = requests.get(f"{COMQTT_API_URL}/config", timeout=2)
        config = config_resp.json() if config_resp.status_code == 200 else {}
        
    except requests.RequestException as e:
        overall_stats = {"error": f"Could not connect to MQTT Broker: {e}"}
        config = {}

    context = {
        "stats": overall_stats,
        "config": config,
    }
    return render(request, 'core/dashboard.html', context)
