# Cuadre de ventas 2026-11 (corrida 2026-11-09 01:14 UTC)

Rango: 2026-11-01 a 2026-11-30. Se cuentan los negocios en la etapa ganada de cada pipeline de ventas con Fecha de facturacion dentro del rango.

## Alertas (lo primero que hay que revisar si Operaciones reporta diferencias)
- Sin alertas: todo negocio ganado del mes quedo contado.

## El mismo soporte de pago en mas de un negocio: 1 casos (0 con el mismo valor)
Mismo archivo y mismo valor = casi seguro venta duplicada. Mismo archivo con valores distintos suele ser un solo pago para varias compras.
- #30624 Martha Lorena Celedon de la Rosa $0 (2026-11-05); #37167 Martha Lorena Celedon de la Rosa $169.400 (2026-11-05)

## Totales contados por pipeline
- Individual (pipeline 2, etapa CERRADO GANADO): 66 negocios, $7.005.500
- Empresarial (pipeline 1, etapa CERRADO GANADO): 2 negocios, $1.648.500
- IFT (pipeline 4, etapa CERRADO MATRICULARO): 0 negocios, $0

## Por asesor (valor contado vs Ingreso en Bitrix de esos mismos negocios)
| Asesor | Tipo | Negocios | Contado | Ingreso Bitrix |
|---|---|---:|---:|---:|
| Bienvenida Lopez Hurtado | Empresarial | 2 | $1.648.500 | $1.648.500 |
| Bienvenida Lopez Hurtado | Individual | 2 | $92.000 | $92.000 |
| Elicenith Carvajalino Del Toro | Individual | 6 | $238.800 | $238.800 |
| Jessica Luque Garcia | Individual | 1 | $103.800 | $103.800 |
| Karen Liseth Cantillo De la Cruz | Individual | 1 | $322.000 | $322.000 |
| Maria Jose Garcia Guaman | Individual | 2 | $1.173.800 | $1.173.800 |
| Martha Cabrera Montes | Individual | 1 | $146.200 | $146.200 |
| Martha Lorena Celedon de la Rosa | Individual | 16 | $1.043.900 | $1.043.900 |
| Oriana Yadith Felizzola Ortega | Individual | 37 | $3.885.000 | $3.885.000 |

## Ganados este mes que NO se cuentan por la Fecha de facturacion (0)
Ninguno.

## Con Fecha de facturacion en el mes pero en otra etapa exitosa (0)
Ninguno.

## Ganados con Fecha de facturacion en el mes en otros pipelines (0)
Ninguno.

## Negocios contados por su Ingreso (productos en $0 o ilegibles) (0)
Ninguno.

## Negocios donde Precio x Cantidad de productos no coincide con el Ingreso (0)
Ninguno.

## Lineas con precio/cantidad sospechosos (0)
Ninguno.

## Negocios creados o cerrados en el mes que NO estan ganados (abiertos o perdidos, con valor) (2)
| ID | Asesor | Pipeline | Etapa | F. creacion | F. facturacion | F. cierre | Ingreso | Detalle |
|---|---|---|---|---|---|---|---:|---|
| 28489 | Oriana Yadith Felizzola Ortega | VENTA EMPRESARIAL | CERRADO PERDIDO | 2026-08-11 | - | 2026-11-03 | $2.460.000 | No esta en la etapa ganada |
| 36984 | Oriana Yadith Felizzola Ortega | VENTA EMPRESARIAL | PROPUESTA ENVIADA | 2026-11-03 | - | 2026-11-03 | $4.368.000 | No esta en la etapa ganada |

## Revision puntual de negocios (1)
| ID | Asesor | Pipeline | Etapa | F. creacion | F. facturacion | F. cierre | Ingreso | Detalle |
|---|---|---|---|---|---|---|---:|---|
| 30843 | Maria Jose Garcia Guaman | VENTA INDIVIDUAL | CERRADO GANADO | 2026-09-01 | 2026-09-01 | 2026-09-01 | $7.092.700 | Revision puntual [cat 2, stage C2:WON, fact. cruda '2026-08-31T19:00:00-05:00'] |

## Campos de servicio en Bitrix (cuantas ventas contadas los traen llenos)
- Fecha de prestación del servicio (UF_CRM_1679953828661, tipo date, multiple=False, 0 opciones): Individual: 17/66, Empresarial: 0/2
    - crudo '2026-11-02T19:00:00-05:00' -> '2026-11-02T19:00:00-05:00'
    - crudo '2026-11-02T19:00:00-05:00' -> '2026-11-02T19:00:00-05:00'
    - crudo '2026-11-02T19:00:00-05:00' -> '2026-11-02T19:00:00-05:00'
- Servicios a utilizar (UF_CRM_1681146110054, tipo enumeration, multiple=True, 18 opciones): Individual: 56/66, Empresarial: 2/2
    - crudo [97] -> 'Recreación'
    - crudo [100] -> 'Teatro'
    - crudo [100] -> 'Teatro'
- Servicios a cotizar (UF_CRM_1681146530307, tipo enumeration, multiple=True, 28 opciones): Individual: 3/66, Empresarial: 0/2
    - crudo [8493] -> 'VACUNACION SANTA MARTA'
    - crudo [8506] -> 'RECREACION. STA MTA'
    - crudo [8506] -> 'RECREACION. STA MTA'
- Lugar de prestación del servicio (UF_CRM_1681147127230, tipo string, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Orden de servicio (UF_CRM_1681148244917, tipo file, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Cotización servicio (UF_CRM_1698765695579, tipo file, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Servicios (UF_CRM_1743799505479, tipo enumeration, multiple=True, 7 opciones): Individual: 0/66, Empresarial: 0/2
- Presentación portafolio de servicios (UF_CRM_1746571632920, tipo double, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Feria de servicios (UF_CRM_1746571663870, tipo double, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Charla de servicios (UF_CRM_1746571681662, tipo double, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Servicio o área solicitante (UF_CRM_68B71BBA2BFC7, tipo enumeration, multiple=False, 13 opciones): Individual: 0/66, Empresarial: 0/2
- En cumplimiento de la Ley 1581 de 2012, autorizo que la información suministrada sea utilizada por Cajamag para realizar inscripción a su Agencia de Empleo y promoción de los servicios y actividades de la Caja.                                  (UF_CRM_1757437583566, tipo enumeration, multiple=False, 2 opciones): Individual: 0/66, Empresarial: 0/2
- Fecha orden de servicio (UF_CRM_1759868249553, tipo date, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Orden de Servicio (UF_CRM_1759868270967, tipo file, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Aprobación Servicios Sociales (P) (UF_CRM_1774136849, tipo boolean, multiple=False, 0 opciones): Individual: 66/66, Empresarial: 2/2
    - crudo '0' -> '0'
    - crudo '0' -> '0'
    - crudo '0' -> '0'
- Fecha sugerida por el servicio para iniciar la promoción (p) (UF_CRM_1775067706043, tipo date, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Fecha de visto bueno del servicio (p) (UF_CRM_1776784114702, tipo date, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2
- Fecha sugerida por el servicio para iniciar promoción  (UF_CRM_1783756151828, tipo date, multiple=False, 0 opciones): Individual: 0/66, Empresarial: 0/2

## Ventas contadas por seccion del catalogo de productos de Bitrix
Sin datos (las lineas no traen producto del catalogo).

Consultas a Bitrix que fallaron tras reintentos: 0 []
