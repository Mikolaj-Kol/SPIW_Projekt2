import yaml
import requests
import time
import subprocess
import random

SIMULATION_MODE = True
PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
CURRENT_CPU_M = 300    

def load_intent(filepath="intent.yaml"):
    with open(filepath, "r") as file:
        return yaml.safe_load(file)

def get_metric(query):
    if SIMULATION_MODE:
        if "amf_session" in query:
            return random.randint(0, 15)  # Losuje od 0 do 15 sesji
        elif "container_cpu_usage" in query:
            return random.uniform(0.1, 0.9) # Losuje CPU od 10% do 90%
        return 0.0

    try:
        response = requests.get(PROMETHEUS_URL, params={'query': query})
        data = response.json()
        if data['status'] == 'success' and data['data']['result']:
            return float(data['data']['result'][0]['value'][1])
        return 0.0
    except Exception as e:
        print(f"[Błąd] Problem z Prometheusem: {e}")
        return 0.0

def scale_upf(new_cpu_m):
    command = [
        "kubectl", "patch", "deployment", "open5gs-upf",
        "-n", "default", "--type=json",
        "-p", f'[{{"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "{new_cpu_m}m"}}]'
    ]
    
    if SIMULATION_MODE:
        print(f"   [SYMULACJA] Wykonano by komendę: {' '.join(command)}")
    else:
        print(f"   [WYKONANIE] Skalowanie UPF do {new_cpu_m}m...")
        subprocess.run(command)

def main():
    global CURRENT_CPU_M
    print("--- Start kontrolera UPF ---")
    intent = load_intent()
    print("Załadowana intencja:", intent)

    while True:
        query_sessions = 'amf_session{service="open5gs-amf-metrics", namespace="default"}'
        sessions = get_metric(query_sessions)

        query_cpu = 'rate(container_cpu_usage_seconds_total{pod=~"open5gs-upf-.*", container="open5gs-upf", namespace="default"}[1m])'
        cpu_usage = get_metric(query_cpu)

        print(f"\n[Status] Sesje: {sessions} | CPU: {cpu_usage:.2f} | Aktualny przydział: {CURRENT_CPU_M}m")

        step = intent['scaling']['step_cpu_m']
        max_cpu = intent['scaling']['max_cpu_m']
        min_cpu = intent['scaling']['min_cpu_m']

        if sessions >= intent['thresholds']['session_warning'] or cpu_usage >= intent['thresholds']['cpu_critical']:
            if CURRENT_CPU_M < max_cpu:
                print("   -> Decyzja: SKALOWANIE W GÓRĘ (Przekroczone progi ostrzegawcze!)")
                CURRENT_CPU_M += step
                scale_upf(CURRENT_CPU_M)
            else:
                print("   -> Decyzja: Brak akcji. Osiągnięto maksymalny limit zasobów.")

        elif sessions <= intent['thresholds']['session_safe'] and cpu_usage <= intent['thresholds']['cpu_safe']:
            if CURRENT_CPU_M > min_cpu:
                print("   -> Decyzja: SKALOWANIE W DÓŁ (Niskie obciążenie, zwalniamy zasoby)")
                CURRENT_CPU_M -= step
                scale_upf(CURRENT_CPU_M)
            else:
                print("   -> Decyzja: Brak akcji. Osiągnięto minimalny limit zasobów.")
        
        else:
            print("   -> Decyzja: Brak akcji. Parametry w normie.")

        time.sleep(4)  # Czekamy 4 sekundy w pętli

if __name__ == "__main__":
    main()
