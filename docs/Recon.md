# Reconnaissance de Portales

Los portales del Congreso de la Union no tienen API oficial y cambian estructura sin aviso. Antes de escribir cualquier scraper, hay que inspeccionar el HTML real y mapear los selectores.

## Por que importa

Escribir un scraper sin recon previo lleva a:
- Horas debuggeando selectores incorrectos
- Reescrituras cuando el portal cambia algo menor
- Campos no detectados que estaban disponibles

Hacer recon primero garantiza que los selectores usados existen hoy.

## Flujo de trabajo

```
1. Correr script de recon -> guarda HTML en Recon/Output/
2. Abrir los HTML en VS Code o navegador local
3. Identificar la estructura: tablas, divs, clases CSS
4. Probar selectores con selectolax en un script de prueba
5. Cuando funcionan, llevarlos al scraper definitivo
```

## Estructura de Recon/Output/

```
Recon/Output/
├── Diputados/
│   ├── ListadoGpnpLxvi.html
│   ├── ListadoEdomexLxvi.html
│   ├── CurriculaSampleLxvi.html
│   ├── AsistenciasSesion20260415.html
│   ├── AsistenciasDiputadoSample.html
│   └── VotacionesListado.html
├── Senado/
│   ├── SenadoresListado.html
│   ├── SenadorDetalleSample.html
│   ├── AsistenciaListado.html
│   └── GacetaListado.html
└── Sil/
    ├── ReporteDiputados.html
    └── ReporteSenado.html
```

Esta carpeta esta en `.gitignore` (HTMLs grandes y cambiantes).

## Identificacion de selectores

### Tablas estilo SITL Diputados

El SITL usa tablas tradicionales con `<table>`, `<tr>`, `<td>`. Patron tipico:

```html
<table class="emite_listado">
  <tr>
    <td><img src="fotos_dip/123.jpg"></td>
    <td><a href="curricula.php?dipt=123">PEREZ GARCIA, JUAN</a></td>
    <td>MORENA</td>
    <td>5</td>
    <td>CDMX</td>
  </tr>
</table>
```

Selector con selectolax:

```python
from selectolax.parser import HTMLParser

# Parsea el listado y extrae datos crudos por fila
# Devuelve lista de dicts con los campos clave
def ParsearListadoDiputados(Html):
    Tree = HTMLParser(Html)
    Resultados = []
    for Fila in Tree.css('table.emite_listado tr'):
        Celdas = Fila.css('td')
        if len(Celdas) < 5:
            continue
        Enlace = Celdas[1].css_first('a')
        if Enlace is None:
            continue
        IdExterno = Enlace.attributes.get('href', '').split('dipt=')[-1]
        Resultados.append({
            'FotoUrl': Celdas[0].css_first('img').attributes.get('src'),
            'IdExterno': IdExterno,
            'NombreCompleto': Enlace.text(strip=True),
            'Partido': Celdas[2].text(strip=True),
            'Distrito': Celdas[3].text(strip=True),
            'Estado': Celdas[4].text(strip=True),
        })
    return Resultados
```

### Senado

El portal del Senado usa HTML mas estructurado con clases descriptivas. Confirmar con recon real.

## Manejo de encoding

Algunos endpoints del SITL devuelven ISO-8859-1 o windows-1252. Sintoma: aparecen secuencias como `JOSE` mal codificadas en lugar de `JOSE` correcto con acento.

Manejo en httpx:

```python
# Descarga URL y normaliza encoding a UTF-8
# Maneja ISO-8859-1 comun en SITL
async def DescargarHtml(Cliente, Url):
    Respuesta = await Cliente.get(Url)
    Bytes = Respuesta.content
    Encoding = Respuesta.charset_encoding or 'iso-8859-1'
    try:
        return Bytes.decode(Encoding)
    except UnicodeDecodeError:
        return Bytes.decode('iso-8859-1', errors='replace')
```

Para deteccion automatica robusta: `charset-normalizer`.

## User-Agent

Sin un User-Agent realista algunos portales bloquean o devuelven HTML diferente:

```python
HeadersNavegador = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
}
```

## Rate limiting consciente

Estos son portales del gobierno con recursos limitados. Ser respetuoso:

- Maximo 1 request por segundo por host
- Backoff exponencial si se reciben 429 o 503
- Evitar correr scrapers masivos en horario pico (9am-3pm CDMX)
- Identificarse con User-Agent o header `From:` en uso intensivo

## Deteccion de cambios de estructura

En cada scraper, validar que los selectores devuelven al menos N elementos esperados. Si no, fallar ruidosamente:

```python
Filas = Tree.css('table.emite_listado tr')
if len(Filas) < 50:
    raise ScraperEstructuraError(
        f"Solo se encontraron {len(Filas)} filas. "
        "La estructura del portal pudo haber cambiado."
    )
```

Esto alerta cuando el HTML cambia, en lugar de fallar silenciosamente.

## Cuando no aparezca lo esperado

Si una URL devuelve 404 o el HTML no contiene lo esperado:

1. Abrir la URL en navegador real con DevTools abierto
2. Network tab: observar que endpoints adicionales se cargan via AJAX
3. Muchos portales del Congreso cargan datos via fetch a endpoints internos `.json` o `.php` que devuelven JSON. Son la mejor opcion si existen.
4. Documentar el endpoint encontrado en `docs/Endpoints.md`
