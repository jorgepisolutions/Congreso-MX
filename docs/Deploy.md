# Deploy en VPS

Guia paso a paso para llevar CongresoMx a un servidor Linux limpio.

## Prerequisitos

- Servidor Linux (recomendado: Ubuntu 24.04 LTS, 4 GB RAM minimo).
- Acceso SSH como `root` o usuario con `sudo` y llave publica instalada en `~/.ssh/authorized_keys`.
- Dominio apuntando al IP publico (registro A en tu DNS). Sin dominio, podes saltar el paso de Caddy y exponer la API en HTTP plano.

Hosting recomendado por `PROJECT.md`: Hetzner CX22 (Ubuntu 24.04, 4 GB RAM, 2 vCPU). Cualquier VPS comparable sirve.

## 1) Provisionar el server

Desde tu Mac:

```bash
# Verifica conectividad
ssh root@<IP_VPS>

# Una vez dentro, actualiza el sistema
apt update && apt upgrade -y
apt install -y curl git ca-certificates ufw
```

## 2) Firewall basico

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

(En el servidor temporal actual saltamos esto. Para prod si lo aplicamos.)

## 3) Instalar Docker + Compose

Script oficial de docker.com:

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# Verificar
docker --version
docker compose version
```

## 4) Clonar el repo

```bash
mkdir -p /usr/local
cd /usr/local
git clone https://github.com/jorgepisolutions/Congreso-MX.git CongresoMX
cd CongresoMX
```

Si el repo es privado, autenticate con PAT via `git config --global credential.helper store` y guarda credenciales en `/root/.git-credentials` con permisos 600.

## 5) Configurar `.env`

```bash
cp .env.example .env
$EDITOR .env
```

Reemplaza los placeholders. **Importante para deploy con docker compose**:

```
DatabaseUrl=mysql+asyncmy://CongresoMx:<PASS>@Mariadb:3306/CongresoMx?charset=utf8mb4
RedisUrl=redis://Redis:6379/0
MariadbRootPassword=<algo robusto>
MariadbUser=CongresoMx
MariadbPassword=<algo robusto>
ApiKey=<no importa, se gestiona via tabla ApiKeys>
```

`Mariadb` y `Redis` son los hostnames internos de docker compose (no `127.0.0.1`).

## 6) Configurar dominio en `Caddyfile`

Edita `Docker/Caddyfile`:

```
api.tudominio.com {
    reverse_proxy AppApi:8000 { ... }
}
```

Asegurate que el dominio resuelve al IP del VPS:

```bash
dig api.tudominio.com +short
# Debe imprimir el IP del VPS
```

## 7) Primer deploy

```bash
# Usa el override Prod (incluye Caddy + HTTPS)
COMPOSE_OVERRIDE=Prod bash Scripts/Deploy.sh
```

Esto:
1. `git pull --ff-only`
2. `docker compose build`
3. Aplica migraciones Alembic
4. Levanta el stack
5. Espera healthy en `/health`

Caddy va a obtener un certificado Let's Encrypt automaticamente (~30 seg) la primera vez.

## 8) Seed inicial

```bash
docker compose -f Docker/DockerCompose.yml -f Docker/DockerCompose.Prod.yml \
  exec AppApi python Scripts/SeedCatalogos.py
```

Carga Legislaturas, Periodos, Estados, Partidos.

## 9) Backfill historico

```bash
docker compose -f Docker/DockerCompose.yml -f Docker/DockerCompose.Prod.yml \
  exec AppApi congresomx Backfill --legislatura LXVI
```

Toma ~70 min (rate limit 1 req/s por host).

## 10) Generar primer API key

```bash
docker compose -f Docker/DockerCompose.yml -f Docker/DockerCompose.Prod.yml \
  exec AppApi congresomx Api Genkey --nombre "operador"
```

Anota el token. No se vuelve a mostrar.

## 11) Verificar todo funciona

Desde tu Mac:

```bash
curl https://api.tudominio.com/health
# {"Status":"ok",...}

curl -H "X-Api-Key: <token>" "https://api.tudominio.com/Legisladores?Limit=3"
# JSON con 3 legisladores
```

Swagger UI:

```
https://api.tudominio.com/docs
```

## 12) Backups diarios

Edita el crontab de root:

```bash
crontab -e
```

Agrega:

```
0 3 * * * source /usr/local/CongresoMX/.env && cd /usr/local/CongresoMX && bash Scripts/Backup.sh >> /var/log/CongresoMx-backup.log 2>&1
```

Esto corre el backup a las 03:00 UTC todos los dias. Por default guarda en `/var/backups/CongresoMx/` con retencion 30 dias.

Para upload remoto (Backblaze B2 / Cloudflare R2):

```bash
apt install -y rclone
rclone config   # configura un remote llamado 'b2' o 'r2'
```

Luego descomentar la seccion de upload en `Scripts/Backup.sh`.

## 13) Auto-restart

Docker compose ya esta configurado con `restart: unless-stopped` en todos los servicios. Si el servidor se reinicia, los containers vuelven solos.

Si quieres forzar el arranque al boot del host (en caso de problemas con el daemon):

```bash
systemctl enable docker
```

## Operacion diaria

| Tarea | Comando |
|---|---|
| Ver estado | `docker compose ps` |
| Logs en vivo | `docker compose logs -f` |
| Restart un servicio | `docker compose restart AppApi` |
| Actualizar codigo | `bash Scripts/Deploy.sh` (o `COMPOSE_OVERRIDE=Prod bash Scripts/Deploy.sh`) |
| Backup manual | `MARIADB_ROOT_PASSWORD=$(grep MariadbRootPassword .env \| cut -d= -f2) bash Scripts/Backup.sh` |
| Generar API key | `docker compose exec AppApi congresomx Api Genkey --nombre "X"` |
| Revocar API key | `docker compose exec AppApi congresomx Api Revoke <Id>` |

## Troubleshooting

- **HTTPS no funciona**: chequea logs de Caddy (`docker logs CongresoMxCaddy`). Comun: dominio no resuelve al IP, o puerto 80/443 bloqueado por firewall del proveedor.
- **AppApi devuelve 500**: chequea `docker logs CongresoMxAppApi`. Causa comun: `.env` con `DatabaseUrl=...@127.0.0.1:3306` (debe ser `@Mariadb:3306`).
- **Mariadb no inicia**: chequea `/var/lib/docker/volumes/<proj>_MariadbData/_data`. Si el data dir esta corrupto, `docker compose down -v` y re-aplicar migraciones (PIERDES DATA).
- **Backup falla**: ejecuta `bash Scripts/Backup.sh` a mano y mira stderr.
