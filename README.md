# CBM-Simple

A simple Condition-Based Monitoring (CBM) stack using MQTT, InfluxDB, Grafana, Prometheus, and custom Python services for simulation and alerting.

## Architecture

- **MQTT Broker**: [Eclipse Mosquitto](https://mosquitto.org/) for device data ingestion.
- **InfluxDB**: Time-series database for storing sensor data.
- **Grafana**: Visualization and dashboarding for InfluxDB data.
- **Prometheus**: Metrics collection and alerting.
- **Simulator**: Simulates device data and publishes to MQTT.
- **Processor/Alerter**: Consumes MQTT data, writes to InfluxDB, checks for alerts, and exposes Prometheus metrics.

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop)
- [Docker Compose](https://docs.docker.com/compose/)

### Setup

1. **Clone the repository**
   ```sh
   git clone git@github.com:oleh-shchur/cbm-simple.git
   cd cbm-simple
   ```

2. **Start all services**
   ```sh
   docker-compose up -d
   ```

3. **Access the services:**
   - **Grafana**: [http://localhost:3000](http://localhost:3000)  
     Login: `admin` / `adminpassword` (change in `docker-compose.yml` for security)
   - **Prometheus**: [http://localhost:9090](http://localhost:9090)
   - **InfluxDB**: [http://localhost:8086](http://localhost:8086)
   - **Processor/Alerter Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)

### Integrating InfluxDB with Grafana

1. Open Grafana and log in.
2. Go to **Configuration → Data Sources → Add data source**.
3. Select **InfluxDB**.
4. Set:
   - **URL**: `http://cbm_influxdb:8086` (or `http://localhost:8086`)
   - **Organization**: `my-cbm-org`
   - **Token**: `mysecretadmintoken`
   - **Bucket**: `cbm_data`
   - **Query Language**: `Flux`
5. Click **Save & Test**.

### Prometheus Scrape Configuration

Prometheus is pre-configured to scrape metrics from the processor_alerter service at `cbm_processor_alerter:8000`.

### Customization

- **Simulator**: Edit `simulator/` to change device simulation logic.
- **Processor/Alerter**: Edit `processor_alerter/` for custom alerting logic or metrics.

### Useful Commands

- View logs:  
  ```sh
  docker-compose logs -f
  ```
- Stop all services:  
  ```sh
  docker-compose down
  ```

## Project Structure

```
CBM-Simple/
├── docker-compose.yml
├── simulator/
├── processor_alerter/
├── prometheus/
│   └── prometheus.yml
├── grafana_data/
├── influxdb_data/
└── mosquitto/
    ├── config/
    ├── data/
    └── log/
```

## License

MIT License

---

**Security Note:**  
Change all default passwords and tokens before deploying in production.