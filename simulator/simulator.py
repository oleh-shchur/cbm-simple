import paho.mqtt.client as mqtt
import time
import json
import os
import random

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
DEVICE_ID = os.getenv("DEVICE_ID", "sim01")
MQTT_TOPIC = f"cbm/data/{DEVICE_ID}"
SIMULATION_INTERVAL = int(os.getenv("SIMULATION_INTERVAL", 5))

current_temperature = 20.0
vibration_level = 0.5

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Simulator [{DEVICE_ID}] connected to MQTT Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
    else:
        print(f"Simulator [{DEVICE_ID}] failed to connect to MQTT, reason code {reason_code}")

def on_publish(client, userdata, mid, reason_code, properties):
    # This callback is not strictly necessary for publishing but good for debug
    # print(f"Message {mid} published with reason code {reason_code}")
    pass

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"simulator-{DEVICE_ID}-pub")
client.on_connect = on_connect
client.on_publish = on_publish

print(f"Simulator [{DEVICE_ID}] attempting to connect to MQTT Broker...")
try:
    client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
except Exception as e:
    print(f"Simulator [{DEVICE_ID}] MQTT connection error: {e}")
    exit(1)

client.loop_start() # Handles reconnects and network traffic

print(f"Simulator for device '{DEVICE_ID}' started. Publishing to '{MQTT_TOPIC}' every {SIMULATION_INTERVAL} seconds.")

try:
    while True:
        # Simulate temperature: tends to increase slowly over time
        current_temperature += random.uniform(-0.2, 1.0) # More likely to increase
        current_temperature = round(max(15.0, min(50.0, current_temperature)), 2) # Keep in a range

        # Simulate vibration: random fluctuations
        vibration_level = round(random.uniform(0.1, 3.0) + (current_temperature - 20) / 10, 2) # Vibration slightly correlated with temp
        vibration_level = round(max(0.0, min(10.0, vibration_level)), 2)


        payload = {
            "device_id": DEVICE_ID,
            "timestamp": time.time(), # Unix timestamp (seconds)
            "temperature_celsius": current_temperature,
            "vibration_mm_s": vibration_level,
            "operating_hours": round(time.time()/3600 % 1000, 1) # Simple uptime simulation
        }
        json_payload = json.dumps(payload)

        result = client.publish(MQTT_TOPIC, json_payload)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[{DEVICE_ID}] Sent: {json_payload} to {MQTT_TOPIC}")
        else:
            print(f"[{DEVICE_ID}] Failed to send message to {MQTT_TOPIC}, rc: {result.rc}")

        time.sleep(SIMULATION_INTERVAL)
except KeyboardInterrupt:
    print(f"Simulator [{DEVICE_ID}] stopping...")
finally:
    client.loop_stop()
    client.disconnect()
    print(f"Simulator [{DEVICE_ID}] disconnected.")