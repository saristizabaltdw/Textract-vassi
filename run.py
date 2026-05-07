"""
Punto de entrada único.

Ejecuta el flujo completo:
  1. Lee el archivo SAP desde S3
  2. Filtra filas inválidas (sin Material Description)
  3. Clasifica cada material en su familia usando family_rules.yaml
  4. Sube el resultado a S3 (clasificados/sap_clasificado_AAAA-MM-DD.xlsx)

Equivalente a: python classify.py --upload
"""
import sys

# Inyectar --upload en argv para que classify.py lo procese
if '--upload' not in sys.argv:
    sys.argv.append('--upload')

from classify import main

if __name__ == '__main__':
    main()
