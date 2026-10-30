# DESIGN.md: Licitar Hoy

Reglas de diseño del sitio. Léelas antes de tocar `site/static/estilos.css` o
las plantillas. Parten de las de Chamba al Toque, con identidad propia. El
objetivo: que el dueño de una pyme entienda en 3 segundos qué compra el
Estado, cuánto (si se sabe), quién lo compra y hasta cuándo puede consultar,
desde un celular y con pocos datos.

## Paleta (variables en `estilos.css`)

| Variable | Claro | Oscuro | Uso |
|---|---|---|---|
| `--papel` | `#f2f4f7` | `#0d1220` | Fondo. Gris frío: **nunca crema** |
| `--tinta` | `#111827` | `#e9edf3` | Texto |
| `--cab` / `--pri` | `#14284b` / `#1d4f91` | `#0f1d38` / `#8db4ff` | Marca (azul marino de documento oficial): cabecera, enlaces, borde superior de tarjeta |
| `--dato` | `#14284b` | `#b9d0ff` | El monto (el dato que más importa) |
| `--acento` | `#ff7a1a` | igual | **Único acento** (naranja de obra): botón de acción, plazo urgente, foco |

Prohibido: crema con terracota u óxido (la "paleta de asistente IA"),
degradados, sombras en reposo y violetas. El naranja es de señalización, no
terracota: no oscurecerlo hacia el marrón.

## Tipografía y forma
- Pila del sistema, sin fuentes web. Jerarquía con peso (800–900) y tamaño, no con color.
- Sin etiquetas en mayúsculas pequeñas con espaciado. Las etiquetas van en oración y en negrita.
- Números tabulares en montos, fechas y conteos. `text-wrap: balance` en títulos.
- Bordes de 1 px, esquinas de 3 a 6 px. Un solo tipo de botón: plano y lleno.

## Componentes
- **Tarjeta:** entidad (gris) → qué se compra (negrita) → monto grande → objeto · tipo · departamento → plazo de consultas → pie con la nomenclatura. Toda la tarjeta es un solo enlace (`::after` absoluto).
- **Plazo:** "Consultas hasta hoy/mañana/el lunes 2 de noviembre". Urgente (≤ 3 días) en etiqueta naranja con texto oscuro.
- **Dato que no viene ≠ dato inventado.** Sin monto: "Monto no publicado". Sin fechas de ofertas o buena pro: se dice que no vienen en los datos abiertos y se manda a la ficha oficial. Nunca se calculan.
- **El departamento es el de la sede de la entidad**, no necesariamente el de ejecución: se rotula así.

## Interacción y accesibilidad (Web Interface Guidelines de Vercel)
- Áreas táctiles de al menos 44 px, foco visible y enlace "Saltar al contenido".
- `touch-action: manipulation`, y `color-scheme` y `theme-color` coherentes con el tema.
- Nada de pop-ups ni anuncios que tapen el aviso. CSS en línea (se minifica en el build), sin JS obligatorio.
- Logo, favicon e imagen para redes: se generan con Gemini (pendiente); mientras tanto, solo el nombre en texto.

## Cómo revisar un cambio (los "ojos")

```sh
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python site/build.py --data out/avisos.json --out public-prev --state out/state-prev.json --base-url http://127.0.0.1:8796
.venv/Scripts/python -m http.server 8796 --directory public-prev
MSYS_NO_PATHCONV=1 .venv/Scripts/python herramientas/mirar.py http://127.0.0.1:8796 / /departamento/cusco/ --out out/capturas
```

En Git Bash hace falta `MSYS_NO_PATHCONV=1` (si no, "/" se convierte en
`C:/Program Files/Git/`). Playwright 1.55 o más nuevo: con 1.48, Edge ya no
arranca (quitó el modo headless viejo). `mirar.py` toma capturas en 390, 768
y 1440 px y avisa de scroll horizontal, áreas táctiles chicas, imágenes sin
medidas y errores de consola. Hay que mirar las capturas, corregir los 3
peores problemas y repetir (máximo 3 rondas).
