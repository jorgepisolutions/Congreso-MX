# Monitoring

Propuesta minima para tener visibilidad operativa de CongresoMx en
hosting definitivo. Pensado para correr sin costo o muy bajo (free tier).

## Que monitorear

1. **Health del API**: `GET /health` debe devolver 200 con JSON `{"Status":"ok"}`.
2. **Containers vivos**: los 4 contenedores (Mariadb, Redis, AppApi, AppScheduler) deben estar `Up` y `healthy`.
3. **Scheduler progresando**: el log debe mostrar `Heartbeat` cada 5 min y `ReconciliacionDiaria` ejecutandose a las 06:00 CDMX.
4. **Backups recientes**: el directorio `/var/backups/CongresoMx/` debe tener un archivo `.sql.gz` de las ultimas 24h.
5. **Disco**: el `/` no debe llenarse (los HTMLs scrapeados y dumps crecen).

## Opciones de implementacion

### Opcion A — Uptime Kuma (recomendado, self-hosted)

Container chico que monitorea endpoints HTTP y notifica si caen.

Agrega a `Docker/DockerCompose.Prod.yml`:

```yaml
services:
  UptimeKuma:
    image: louislam/uptime-kuma:1
    container_name: CongresoMxUptimeKuma
    restart: unless-stopped
    volumes:
      - UptimeKumaData:/app/data
    ports:
      - "3001:3001"
    networks:
      - CongresoMxNet

volumes:
  UptimeKumaData:
```

Setup post-deploy:
1. Abrir `http://<IP>:3001` (o detras de Caddy con `uptime.tudominio.com`)
2. Crear cuenta admin
3. Agregar monitors:
   - HTTP(s) → `https://api.tudominio.com/health` cada 60s
   - HTTP keyword → mismo URL, esperar string `"Status":"ok"` en respuesta
   - Docker → ping local de cada contenedor cada 5 min
4. Configurar notifications: Telegram, Discord, email, etc.

### Opcion B — Service externo gratuito

- **UptimeRobot** (free 50 monitors, intervalos 5 min): registra `api.tudominio.com/health`, configura email.
- **BetterStack / Better Uptime** (free tier basico): similar.

Ventaja: si tu VPS muere, te enteras desde otro lado.
Desventaja: monitor cada 5 min minimo en free tier; menos granular.

### Opcion C — Script bash + cron

Si no quieres ningun servicio extra, en el mismo VPS:

```bash
# /usr/local/bin/healthcheck.sh
#!/usr/bin/env bash
set -e
if ! curl -sf -m 10 http://localhost:8000/health > /dev/null; then
    # Notifica via email (require ssmtp o similar)
    echo "CongresoMx API caida" | mail -s "ALERTA CongresoMx" tu@email.com
    # O via webhook a Slack/Discord
    # curl -X POST -H 'Content-Type: application/json' \
    #   --data '{"text":"CongresoMx API caida"}' \
    #   "$SLACK_WEBHOOK"
fi
```

Cron cada 5 min:
```
*/5 * * * * /usr/local/bin/healthcheck.sh
```

Limitacion: si el VPS entero se cae, el cron no corre, no avisas.

## Metricas operativas via SQL

Queries utiles para chequear "health logico" semanal:

```sql
-- Latencia entre fecha real y fecha mas reciente en DB
SELECT
  Camara,
  MAX(s.Fecha) AS UltimaSesion,
  DATEDIFF(CURDATE(), MAX(s.Fecha)) AS DiasDeRetraso
FROM Sesiones s GROUP BY Camara;

-- ScrapingRuns recientes con su status
SELECT Id, Tipo, Status, RegistrosNuevos, Errores,
       FinishedAt, TIMESTAMPDIFF(MINUTE, StartedAt, FinishedAt) AS DuracionMin
FROM ScrapingRuns ORDER BY Id DESC LIMIT 10;

-- ApiKeys activas y su uso
SELECT Id, Nombre, Activo, LastUsedAt FROM ApiKeys ORDER BY Id;
```

## Alertas que valen la pena

- **API down >5 min**: critico, alerta inmediata.
- **AppScheduler down**: no se actualizan los datos. Alerta despues de 30 min.
- **Reconciliacion diaria fallo**: chequear logs del scheduler a las 07:00 CDMX (debio correr a las 06:00).
- **Backup no se hizo en >36 horas**: la retencion empieza a comer datos buenos.
- **Disco /var/lib/docker > 80%**: docker prune + limpiar backups viejos.

## Que NO vale la pena (en este punto)

- Prometheus + Grafana stack completo (overkill para una API publica simple).
- ELK / Loki (logs centralizados no son problema con `docker logs`).
- APM (DataDog / New Relic): caro y sin valor sin volumen real.
- Pagers (PagerDuty / OpsGenie): no es servicio 24/7 critico.

Cuando crezca el trafico (tipo 10k req/dia consistente), reconsiderar.
