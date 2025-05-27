import paho.mqtt.client as mqtt
import json
import os
import time
import threading
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError
from prometheus_client import start_http_server, Counter, Gauge

# MQTT Configuration
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
MQTT_TOPIC_SUBSCRIBE = "cbm/data/#" # Subscribe to all devices under this prefix

# InfluxDB Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "mysecretadmintoken")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "my-cbm-org")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "cbm_data")

# Alerting Configuration
ALERT_THRESHOLD_TEMP = float(os.getenv("ALERT_THRESHOLD_TEMP", 35.0))
ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", 10))
ALERT_COOLDOWN_SECONDS = 60 # Cooldown per device before re-alerting
device_alert_states = {} # device_id: {"alerted_temp": False, "last_alert_time_temp": 0}

influx_client = None
write_api = None
query_api = None

def setup_influxdb():
    global influx_client, write_api, query_api
    retry_delay = 5
    max_retries = 12 # Try for up to a minute
    for attempt in range(max_retries):
        try:
            print(f"Processor: Attempting to connect to InfluxDB at {INFLUXDB_URL} {INFLUXDB_TOKEN} (Attempt {attempt + 1}/{max_retries})...")
            influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG, timeout=20000)
            write_api = influx_client.write_api(write_options=SYNCHRONOUS)
            query_api = influx_client.query_api()
            health = influx_client.health()
            if health.status == "pass":
                print(f"Processor: Successfully connected to InfluxDB. Org: {INFLUXDB_ORG}, Bucket: {INFLUXDB_BUCKET}")
                return True
            else:
                print(f"Processor: InfluxDB health check failed: {health.message}")
        except Exception as e:
            print(f"Processor: Error connecting to InfluxDB: {e}")

        if attempt < max_retries - 1:
            print(f"Processor: Retrying InfluxDB connection in {retry_delay} seconds...")
            time.sleep(retry_delay)
        else:
            print("Processor: Max InfluxDB connection retries reached. Exiting.")
            return False
    return False

def on_connect_mqtt(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Processor: Connected to MQTT Broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        client.subscribe(MQTT_TOPIC_SUBSCRIBE)
        print(f"Processor: Subscribed to MQTT topic: {MQTT_TOPIC_SUBSCRIBE}")
    else:
        print(f"Processor: Failed to connect to MQTT, reason code {reason_code}")

def on_message_mqtt(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        # print(f"Processor: Received message: {payload_str} from topic {msg.topic}")
        data = json.loads(payload_str)

        device_id = data.get("device_id", "unknown_device")
        timestamp_ns = int(data.get("timestamp") * 1_000_000_000) # Convert seconds to nanoseconds

        point = Point("machine_metrics") \
            .tag("device_id", device_id) \
            .time(timestamp_ns, WritePrecision.NS)

        for key, value in data.items():
            if key not in ["device_id", "timestamp"] and isinstance(value, (int, float)):
                point = point.field(key, value)

        if write_api:
            try:
                write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
                print(f"Processor: Data written to InfluxDB for {device_id}: {payload_str}")
            except InfluxDBError as e:
                print(f"Processor: InfluxDB write error for {device_id}: {e}")
            except Exception as e:
                print(f"Processor: Unexpected error during InfluxDB write for {device_id}: {e}")
        else:
            print("Processor: Write API not initialized. Cannot write to InfluxDB.")

    except json.JSONDecodeError:
        print(f"Processor: Error decoding JSON: {msg.payload.decode()}")
    except Exception as e:
        print(f"Processor: Error processing MQTT message: {e}")
# Prometheus metrics
temperature_alerts_total = Counter(
    "temperature_alerts_total",
    "Total number of temperature alerts triggered",
    ["device_id"]
)
temperature_gauge = Gauge(
    "device_temperature_celsius",
    "Latest temperature per device",
    ["device_id"]
)

def check_for_alerts():
    if not query_api:
        # print("Processor: Alert check - Query API not available.")
        return

    # print("\n--- Processor: Checking for Alerts ---")
    current_time = time.time()

    # Query for latest temperature for all devices
    flux_query_temp = f'''
        from(bucket: "{INFLUXDB_BUCKET}")
          |> range(start: -5m) // Check recent data to get the latest
          |> filter(fn: (r) => r["_measurement"] == "machine_metrics")
          |> filter(fn: (r) => r["_field"] == "temperature_celsius")
          |> group(columns: ["device_id"])
          |> last()
          |> yield(name: "last_temp")
    '''
    try:
        tables = query_api.query(query=flux_query_temp, org=INFLUXDB_ORG)
        for table in tables:
            for record in table.records:
                device_id = record.values.get("device_id")
                temp = record.get_value()

                # Update Prometheus gauge
                temperature_gauge.labels(device_id=device_id).set(temp)
                if device_id not in device_alert_states:
                    device_alert_states[device_id] = {"alerted_temp": False, "last_alert_time_temp": 0}

                state = device_alert_states[device_id]

                if temp > ALERT_THRESHOLD_TEMP:
                    if not state["alerted_temp"] or (current_time - state["last_alert_time_temp"] > ALERT_COOLDOWN_SECONDS):
                        print(f"🚨 ALERT! Device {device_id}: Temperature {temp}°C EXCEEDS threshold {ALERT_THRESHOLD_TEMP}°C.")
                        state["alerted_temp"] = True
                        state["last_alert_time_temp"] = current_time
                        # Increment Prometheus counter
                        temperature_alerts_total.labels(device_id=device_id).inc()
                elif state["alerted_temp"] and temp <= (ALERT_THRESHOLD_TEMP - 1.0): # Hysteresis: Temp must drop a bit
                    print(f"✅ RESOLVED! Device {device_id}: Temperature {temp}°C is back to normal.")
                    state["alerted_temp"] = False
                    state["last_alert_time_temp"] = 0 # Reset alert time

    except InfluxDBError as e:
        print(f"Processor: InfluxDB query error during alert check: {e}")
    except Exception as e:
        print(f"Processor: Unexpected error during alert check: {e}")
    # print("--- Processor: Alert Check Complete ---\n")

def alert_scheduler():
    print("Processor: Alert scheduler thread started.")
    while True:
        if query_api: # Only run if InfluxDB is connected
            check_for_alerts()
        else:
            print("Processor: Alert scheduler - InfluxDB not ready, skipping check.")
        time.sleep(ALERT_CHECK_INTERVAL)

if __name__ == "__main__":
    
    start_http_server(8000)
    print("Prometheus metrics available at http://localhost:8000/metrics")
    if not setup_influxdb():
        exit(1)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="processor-alerter-sub")
    mqtt_client.on_connect = on_connect_mqtt
    mqtt_client.on_message = on_message_mqtt

    print(f"Processor: Attempting to connect to MQTT Broker {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")
    try:
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
    except Exception as e:
        print(f"Processor: MQTT connection error: {e}")
        if influx_client:
            influx_client.close()
        exit(1)

    mqtt_client.loop_start()

    alert_thread = threading.Thread(target=alert_scheduler, daemon=True)
    alert_thread.start()

    print("Processor and Alerter service started. Waiting for messages...")
    try:
        while True:
            time.sleep(1) # Keep main thread alive for KeyboardInterrupt
    except KeyboardInterrupt:
        print("Processor and Alerter stopping...")
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        if influx_client:
            influx_client.close()
        print("Processor and Alerter disconnected and closed.")