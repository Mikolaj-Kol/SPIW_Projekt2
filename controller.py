import time
import requests
import yaml
import subprocess

SIMULATION_MODE = False
PROMETHEUS_URL = "http://192.168.0.202:9090/api/v1/query"

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

def scale_upf(new_cpu_m):
    command = [
        "kubectl", "patch", "deployment", "open5gs-upf",
        "-n", "default", "--type=json",
        "-p", f'[{{"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/cpu", "value": "{new_cpu_m}m"}}, {{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "{new_cpu_m}m"}}]'
    ]
    
    if SIMULATION_MODE:
        print(f"   [SYMULACJA] Wykonano by komendę: {' '.join(command)}")
    else:
        print(f"   [WYKONANIE] Skalowanie UPF do {new_cpu_m}m (requests oraz limits)...")
        subprocess.run(command)

def main():
    print("--- Start kontrolera UPF ---")
    intent = load_intent()
    print(f"Załadowana intencja: {intent}\n")

    current_cpu_m = 300
    
    while True:
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

if _name_ == "_main_":
    main()
