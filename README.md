# Clasificador de Materiales SAP

Pipeline para leer el catálogo de materiales SAP desde S3, clasificar cada
material en una familia (PAPEL, TELA, CARTON, etc.) y subir el resultado
clasificado de vuelta a S3.

## ¿Qué hace?

El comando `python run.py` ejecuta el flujo completo:

1. **Descarga** el archivo `Price List MP SAP Ago-2025.xlsx` desde S3
2. **Filtra** filas inválidas (sin `Material Description` — basura del export)
3. **Clasifica** cada material en una familia usando reglas definidas en
   `family_rules.yaml`
4. **Redondea** las columnas numéricas para que el Excel se vea bien
5. **Sube** el resultado a S3 con nombre versionado por fecha:
   `s3://<BUCKET>/<S3_OUTPUT_PREFIX>/sap_clasificado_AAAA-MM-DD.xlsx`

## Estructura del proyecto

```
.
├── run.py                # Punto de entrada único — corre todo
├── classify.py           # Lógica de clasificación
├── s3_utils.py           # Utilidades de acceso a S3
├── family_rules.yaml     # Reglas de clasificación (editable sin tocar código)
├── requirements.txt      # Dependencias Python
├── Dockerfile            # Imagen Docker
├── .env.example          # Plantilla de variables de entorno
└── README.md             # Este archivo
```

## Configuración

### 1. Variables de entorno

```dotenv
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

S3_BUCKET=sigmaq
S3_INPUT_PREFIX=bedrock/Cajas Especiales Drive/Archivos Excel-CSV/Materiales/
S3_OUTPUT_PREFIX=clasificados/
```
## Ejecución

### Opción A: localmente con Python

Instalar dependencias y correr:

```bash
pip install -r requirements.txt
python run.py
```

### Opción B: con Docker

Construir la imagen:

```bash
docker build -t sigma-classifier .
```

Ejecutar (le pasamos el `.env` con las credenciales):

```bash
docker run --rm --env-file .env sigma-classifier
```

## Otros comandos útiles

`classify.py` también acepta flags individuales para inspección:

```bash
# Solo clasifica y muestra distribución (NO sube nada)
python classify.py

# Muestra todos los materiales que cayeron en una familia específica
python classify.py --familia OTROS
python classify.py --familia TELA

# Muestra una muestra aleatoria de 30 materiales clasificados
python classify.py --sample 30

# Clasifica y sube (igual que run.py)
python classify.py --upload
```

## Cómo agregar/modificar familias

Las reglas viven en `family_rules.yaml`. **No hay que tocar Python para
cambiar las clasificaciones.**

Estructura:

```yaml
default_familia: OTROS

rules:
  - familia: TELA
    match_name:
      starts_with: ["TELA ", "FABRIC "]

  - familia: PAPEL
    match_name:
      contains_any: [rainbow, kurz, foil, paper]

  - familia: QUIMICO
    match_unit: [GAL, L]
```

### Reglas de oro

1. **Las reglas se evalúan top-down**: la primera que matchea, gana
2. **Reglas específicas arriba**, generales abajo
3. Las comparaciones son **case-insensitive**
4. Si nada matchea, se asigna `default_familia` (OTROS)

### Tipos de condiciones

| Campo | Qué hace |
|-------|----------|
| `starts_with` | El nombre debe empezar con alguno de estos prefijos |
| `contains_any` | El nombre debe contener al menos una de estas substrings |
| `contains_all` | El nombre debe contener TODAS estas substrings |
| `not_contains` | El nombre NO debe contener ninguna de estas (negación) |
| `match_unit` | La unidad de medida (BUn) debe ser una de estas |

### Iteración recomendada

Cuando se agregan reglas o se ajustan:

```bash
# 1. Editar family_rules.yaml
# 2. Ver qué quedó en OTROS para detectar reglas que faltan
python classify.py --familia OTROS

# 3. Verificar que las reglas existentes siguen funcionando bien
python classify.py --familia TELA
python classify.py --familia PAPEL

# 4. Cuando esté correcto, subir
python run.py
```
