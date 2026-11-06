# Evaluación de transcripciones: instrucciones para el agente (Codex o Antigravity)

Eres el **orquestador**. No calificas nada tú. Por cada transcripción lanzas un subagente nuevo, le das exactamente lo que se indica abajo y guardas su respuesta sin tocarla.

Estás en la carpeta de la corrida. Todas las rutas de estas instrucciones son relativas a ella.

## 1. Antes de empezar

Mira qué modelo está seleccionado en esta conversación y busca su carpeta:

| Modelo | Carpeta de salida |
|---|---|
| `gpt-6-astra` | `A3_gpt_astra_6/` |
| `gpt-6.1-sol` | `A4_gpt_sol_6.1/` |

- Si el modelo seleccionado no está en la tabla, **detente** y avísale a Ricardo. No elijas otra carpeta.
- Todos los subagentes usan el mismo modelo que esta conversación. No cambies de modelo.
- **En Codex, todos los subagentes corren con esfuerzo de razonamiento `high`.** Si los lanzas con `codex exec`, agrega siempre `-c model_reasoning_effort="high"`. Si no puedes fijarlo en `high`, **detente** y avísale a Ricardo; no sigas con otro nivel.
- Lee solo lo que está en `config_externos/` y escribe solo en tu carpeta de salida. No abras ninguna otra carpeta ni archivo de la corrida: ni `config_claude/`, ni `textos.json`, ni las carpetas de los otros modelos (`A…`, `R_…`).

## 2. Por cada código de `config_externos/mensajes/` (E01 … E32) cuya salida todavía no exista

1. Lanza un **subagente nuevo**, con contexto limpio y el mismo modelo. Un subagente por transcripción: ninguno ve otra transcripción ni otra respuesta.
2. Dale exactamente esto, sin agregar, quitar ni resumir nada:
   - **Instrucciones:** el contenido completo de `config_externos/sistema_evaluador.txt`.
   - **Mensaje:** el contenido completo de `config_externos/mensajes/<código>.txt`.
   - **Formato de respuesta** (agrégalo al final del mensaje, tal cual):

     > Responde solo con un objeto JSON, sin texto antes ni después, con esta forma: {"capacidades": [{"n": 1, "slug": "nbs_definition", "nivel": <entero>, "evidencia": ["<cita literal>", ...], "justificacion": "<párrafo>"}, ...]}. Incluye las 7 capacidades en el orden de la rúbrica, con su número (n) y su slug.
3. Guarda la respuesta del subagente, tal cual, en `<carpeta de salida>/<código>.json`. No la corrijas, no cambies niveles ni citas, no la resumas.
4. Si la respuesta no es un JSON válido con 7 capacidades, repítela con otro subagente nuevo (como máximo dos veces más). Si sigue mal, anota el código en `<carpeta de salida>/errores.txt` y sigue con la siguiente.

Puedes lanzar varios subagentes en paralelo, siempre uno por transcripción. Los scripts o archivos auxiliares que necesites (por ejemplo, para lanzar los subagentes) van dentro de tu carpeta de salida, nunca en otra parte.

## 3. Prohibido

- Calificar tú mismo, revisar o "mejorar" las respuestas de los subagentes.
- Poner dos transcripciones en el mismo subagente o en el mismo contexto.
- Modificar cualquier cosa de `config_externos/` (`sistema_evaluador.txt`, `mensajes/`, los esquemas).
- Leer archivos fuera de `config_externos/` o escribir fuera de tu carpeta de salida.

## 4. Al terminar

Escribe en `<carpeta de salida>/_registro.txt`:
- la herramienta (Codex o Antigravity) y su versión, si la muestra;
- el nombre exacto del modelo que muestra el selector;
- el esfuerzo de razonamiento con que corrieron los subagentes;
- la fecha y la hora;
- cuántas transcripciones quedaron guardadas y cuáles fallaron.
