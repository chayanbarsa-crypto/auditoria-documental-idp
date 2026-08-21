# Panel de resolución de LuzIA

Genera un panel HTML autónomo (un solo archivo, sin dependencias externas) a
partir del export de Salesforce de los chats de LuzIA con instaladores.

```bash
pip install pandas openpyxl
python dashboard/generar_dashboard.py Junio21Agosto.xlsx
# -> dashboard/salida/panel_luzia.html
```

## Qué muestra

- **KPIs**: chats analizados, porcentaje de acierto (`status = RESUELTA`),
  acierto con parciales, sin resolver y porcentaje que solicita agente
  (`sf_requested_agent`).
- **Evolución mes a mes** con el reparto de estados y los días cubiertos por mes.
- **Real frente a usuario de pruebas**: comparativa fija entre los chats reales
  y los del usuario `CLIENTE EXTERNO EXTERNO`.
- **Qué preguntan**: categoría principal (`specific_category`), subcategoría
  (`category_subtype`), línea de negocio y categoría general.
- **Cómo termina**: quién cierra el chat, sentimiento y petición de agente.
- **Por qué no resuelve**: motivos de `no_resolution_reason` más repetidos.
- **Detalle** de conversaciones con buscador.

Filtros: tipo de chat (reales / pruebas / todos), mes, línea de negocio y
categoría principal.

## Criterios

- La vista arranca en **chats reales**: el usuario `CLIENTE EXTERNO EXTERNO`
  son pruebas internas y falsearían el acierto.
- El export trae dos filas de cola (una vacía y la de «Filtros aplicados») que
  se descartan por no tener `status`.
- Si la columna `TIPO` viniera vacía, el tipo se deduce del nombre del usuario.

## Datos

Ni el export ni el HTML generado se versionan: llevan nombres de instaladores y
resúmenes de conversaciones con clientes. `.gitignore` cubre `dashboard/salida/`
y los `.xlsx`.
