# cliproxyaccount

Configuración desplegada de [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
(`router-for-me/CLIProxyAPI`, rama `main`) tal como corre en el contenedor
`ia-local` (10.10.1.92) de Proxmox. Expone un endpoint compatible con
OpenAI/Gemini/Claude en el puerto `8317` que reparte peticiones entre varias
cuentas de Google Antigravity con failover automático.

Este repo guarda la **configuración**, no el código del proxy: el binario se
compila desde el propio `router-for-me/CLIProxyAPI` en el servidor.

## Qué hay aquí

| Fichero | Qué hace |
|---|---|
| `config.yaml` | Configuración del proxy: puerto, claves, catálogo de modelos, gestión remota |
| `cli-proxy-api.service` | Unidad systemd que arranca el proxy con `--local-model` |
| `cliproxy-models-sync.service` / `.timer` | Resincroniza el catálogo con upstream cada 3h sin perder los modelos añadidos a mano |
| `sync-models.sh` | Descarga el catálogo de upstream, lo fusiona, reconstruye y solo sustituye el binario si el health-check pasa |
| `merge_models.py` | Inyecta en `models.json` los modelos que Google devuelve para esta cuenta pero que upstream aún no declara (ahora mismo: `gemini-3.6-flash-medium` y `-low`) |
| `declare_models.py` | Declara en Hermes los modelos de cada proveedor (`llamacpp`, `antigravity`), leyendo las claves del entorno |

## Por qué `--local-model`

El proxy trae su propio catálogo de modelos y lo actualiza solo desde
upstream. El problema: Google expone `gemini-3.6-flash-medium` y
`gemini-3.6-flash-low` para esta cuenta, pero el catálogo de
`router-for-me/CLIProxyAPI` todavía no los declara — si dejamos que el proxy
se autoactualice, cada resync **borra** esos dos modelos.

La solución es `--local-model` (usa solo el catálogo embebido en el binario,
nunca lo descarga solo) más `merge_models.py`, que fusiona upstream + las
rutas añadidas a mano antes de compilar. El timer de 3h reproduce el mismo
ritmo que traía el autoupdate de CLIProxyAPI, pero pasando siempre por la
fusión.

## Cuentas y failover

El pool de cuentas OAuth vive en `~/.cli-proxy-api/*.json` en el servidor
(no en este repo: son credenciales, no configuración). Actualmente hay 3
cuentas de Google Antigravity. El proxy rota entre ellas y, si una devuelve
429, reintenta con la siguiente — así una única cuenta agotada no tumba el
servicio.

Con `debug: true` en `config.yaml`, el log de systemd
(`journalctl -u cli-proxy-api`) escribe una línea por petición con el formato:

```
Use OAuth provider=antigravity auth_file=antigravity-<email>.json for model <modelo>
```

Es la única forma de ver qué cuenta atendió qué petición: el proxy no lo
expone por API. El [panel de GPU e inferencia LLM en
Proxmox](http://10.10.1.4:8088) lee esa línea (vía `pct exec 110`) y muestra
en vivo, por cada modelo con actividad en los últimos 30 minutos, qué cuenta
lo está sirviendo.

## Desplegar / actualizar

```bash
# en el servidor (10.10.1.92)
cd /root/CLIProxyAPI
git pull
bash scripts/sync-models.sh        # fusiona catálogo, reconstruye, verifica, sustituye
systemctl restart cli-proxy-api
```

## Secretos (NO están en este repo)

`config.yaml` aquí tiene `secret-key` y la primera entrada de `api-keys`
sustituidas por marcadores `CAMBIA_ESTO__...`. Los valores reales viven solo
en `/root/CLIProxyAPI/config.yaml` en el servidor. Las credenciales OAuth de
cada cuenta (`~/.cli-proxy-api/*.json`) tampoco se suben — son tokens, no
configuración, y el `.gitignore` de este repo los bloquea explícitamente.

Si copias este `config.yaml` para desplegar en otro sitio:

1. Genera una `api-keys` nueva (una cadena aleatoria larga) — es la clave que
   usan los clientes del proxy (Hermes, el pipeline de contenido, etc.).
2. Pon esa misma clave en texto plano en `secret-key`; el proxy la hashea con
   bcrypt solo al arrancar.
3. Vuelve a autorizar cada cuenta de Google Antigravity (el flujo OAuth genera
   los `.json` de `~/.cli-proxy-api/`).
