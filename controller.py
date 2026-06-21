import time
import requests
import yaml
import subprocess

SIMULATION_MODE = False
PROMETHEUS_URL = "http://192.168.20.202:9090/api/v1/query"

def load_intent():
    with open('intent.yaml', 'r') as file:
        return yaml.safe_load(file)

def get_metric(query):
    if SIMULATION_MODE:
        return 0.0
    try:
        response = requests.get(PROMETHEUS_URL, params={'query': query})
        results = response.json()['data']['result']
        if results:
            return float(results[0]['value'][1])
        return 0.0
    except Exception as e:
        print(f"[Błąd] Problem z Prometheusem: {e}")
        return 0.0

def get_upf_pod_name():
    if SIMULATION_MODE:
        return "open5gs-upf-symulacja"
    try:
        command = ["kubectl", "get", "pods", "-n", "default", "--no-headers", "-o", "custom-columns=:metadata.name"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if line.startswith("open5gs-upf-"):
                return line.strip()
    except Exception as e:
        print(f"[Błąd] Nie udało się pobrać nazwy Poda: {e}")
    return None

def scale_upf(new_cpu_m):
    pod_name = get_upf_pod_name()
    if not pod_name:
        print("   [Błąd] Brak Poda UPF do przeskalowania.")
        return

    command = [
        "kubectl", "patch", "-n", "default", "pod", pod_name,
        "--subresource", "resize", "--patch", 
        f'{{"spec":{{"containers":[{{ "name":"open5gs-upf", "resources":{{"limits":{{"cpu":"{new_cpu_m}m"}} }} }}]}}}}'
    ]
    
    if SIMULATION_MODE:
        print(f"   [SYMULACJA] Wykonano by komendę: {' '.join(command)}")
    else:
        print(f"   [WYKONANIE] Skalowanie in-place Poda {pod_name} do {new_cpu_m}m...")
        subprocess.run(command)

def main():
    print("--- Start kontrolera UPF ---")
    current_cpu_m = 300
    
    while True:
        intent = load_intent()
        
        sessions = get_metric('amf_session{service="open5gs-amf-metrics", namespace="default"}')
        cpu_usage = get_metric('rate(container_cpu_usage_seconds_total{pod=~"open5gs-upf-.*", container="open5gs-upf", namespace="default"}[1m])')

        print(f"[Status] Sesje: {sessions} | CPU: {cpu_usage:.2f} | Aktualny przydział: {current_cpu_m}m")

        step = intent['scaling']['step_cpu_m']
        max_cpu = intent['scaling']['max_cpu_m']
        min_cpu = intent['scaling']['min_cpu_m']

        if sessions >= intent['thresholds']['session_warning'] or cpu_usage >= intent['thresholds']['cpu_critical']:
            if current_cpu_m < max_cpu:
                current_cpu_m += step
                print("   -> Decyzja: SKALOWANIE W GÓRĘ (Przekroczone progi ostrzegawcze!)")
                scale_upf(current_cpu_m)
            else:
                print("   -> Decyzja: Brak akcji. Osiągnięto maksymalny limit zasobów.")
                
        elif sessions <= intent['thresholds']['session_safe'] and cpu_usage <= intent['thresholds']['cpu_safe']:
            if current_cpu_m > min_cpu:
                current_cpu_m -= step
                print("   -> Decyzja: SKALOWANIE W DÓŁ (Niskie obciążenie, zwalniamy zasoby)")
                scale_upf(current_cpu_m)
            else:
                print("   -> Decyzja: Brak akcji. Osiągnięto minimalny limit zasobów.")
        else:
            print("   -> Decyzja: Brak akcji. Parametry w normie.")

        print("")
        time.sleep(4)

if __name__ == "__main__":
    main()
