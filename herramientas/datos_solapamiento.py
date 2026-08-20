# -*- coding: utf-8 -*-
"""Analisis de solapamiento entre los 4 documentos de modificaciones."""

DOCS = [
 ('6292',    '000006292 Procedimiento para realizar modificaciones tecnicas', 'Procedimiento', '2 pag'),
 ('6601',    '000006601 Modificaciones administrativas',                      'Procedimiento', '4 pag'),
 ('FAQ-ADM', 'FAQs MODIFICACIONES ADMINISTRATIVAS (plantilla FE)',            'FAQ',           '6 pag'),
 ('FAQ-CON', '20260414 FAQs Modificaciones de contrato (plantilla fenie)',    'FAQ',           '4 pag'),
]

# tema, 6292, 6601, FAQ-ADM, FAQ-CON, n_docs, riesgo, nota
TEMAS = [
 ('Modificar producto', '', 'Sec.1', 'Sec.1', 'Sec.2 y 3', 'Tres fuentes para el mismo tramite'),
 ('Producto de precio fijo NO se puede modificar', '', 'Sec.1', 'OMITE', 'Sec.3',
  'Restriccion critica ausente en el compendio que mas se recupera'),
 ('Datos de cliente', '', 'Sec.2', 'Sec.2', 'Sec.4 (lista)', ''),
 ('Representante', '', 'Sec.3', 'Sec.3', 'Sec.4 (lista)', ''),
 ('Autorizado', '', 'Sec.4', 'Sec.4', 'Sec.4 (lista)', ''),
 ('Datos de Contacto del PS', '', 'Sec.5', 'Sec.5', 'Sec.4 (lista)', ''),
 ('Contacto PS: solo telefono espanol (+34)', '', 'Sec.5', 'OMITE', '',
  'Restriccion ausente en el compendio. Nuestra pregunta E04 solo acerto porque gano 6601'),
 ('Correo de facturacion', '', 'Sec.6.4', 'Sec.6', '', ''),
 ('Cuenta bancaria', '', 'Sec.6.2', 'Sec.7', 'Sec.7 (masiva)', 'Tres fuentes'),
 ('Direccion de facturacion', '', 'Sec.6.3', 'Sec.8', '', 'Pasos CONTRADICTORIOS: ver hoja 03'),
 ('Metodo de pago codigo de barras', '', 'Sec.6.1', 'OMITE', '', ''),
 ('Datos del contrato', 'Lo menciona', 'Sec.7', 'Sec.9', 'Sec.4 (lista)',
  'Cuatro fuentes. 6292 admite que es administrativa y aun asi la incluye'),
 ('Tipo de firma: opcion PAPEL', '', 'Sec.7', 'OMITE', '',
  'FAQ-ADM solo dice Distancia o Presencial'),
 ('Remesa fija', '', 'Sec.8', 'Sec.10', 'Sec.4 (lista)', ''),
 ('Remesa fija: coste', '', 'Sec.8', 'Sec.10', '', 'Los dos coinciden: 1% fijo / 1,2 EUR-MWh o 1,6 EUR-mes'),
 ('Monedero Solar', 'Sec.1 lo menciona', 'Sec.9', 'Sec.11', 'Sec.4 (lista)', 'CUATRO fuentes'),
 ('Monedero Solar: al desactivar se pierde el saldo', '', 'OMITE', 'Sec.11', '',
  'Aviso critico solo en el compendio. El procedimiento oficial solo dice: puede desactivarse, si'),
 ('Autoconsumo', 'Sec.1', '', '', 'Sec.9', ''),
 ('Tarifa / Tension / Potencias', 'Sec.2', '', '', 'Sec.4 (lista)', ''),
 ('Maximetro', 'Sec.3', '', '', 'Sec.4 y 10', ''),
 ('Maximetro: potencia segun CIE/boletin', 'Sec.3', '', '', 'Sec.10',
  'Tambien en 000006590 pag.13, casi palabra por palabra. TRES documentos con la misma regla'),
 ('Propiedad del contador', 'Sec.4', '', '', '', 'Unico tema sin solapar'),
 ('Cambio de titular con modificaciones', '', '', '', 'Sec.1', ''),
 ('Baja de contrato / bajas temporales', '', '', '', 'Sec.5 y 6', ''),
 ('Modificaciones simultaneas', '', 'Intro', '', 'Sec.11',
  'CONTRADICCION directa: ver hoja 03'),
 ('Modificacion con renovacion en curso', '', '', '', 'Sec.4 y 11', ''),
]

CONTRADICCIONES = [
 ('Direccion de facturacion: paso final', 'ALTA',
  '000006601 Sec.6.3',  'se pulsa "Normalizar" y despues "Guardar"',
  'FAQs MODIF ADMIN Sec.8', 'Pulsa "Guardar sin normalizar". Pulsa "Crear". Pulsa "Guardar"',
  'Dos pasos operativos opuestos. El agente hara uno u otro segun que documento gane el ranking'),
 ('Contacto del PS: telefono extranjero', 'ALTA',
  '000006601 Sec.5', 'Es obligatorio incluir un numero de telefono movil espanol valido. "Puedo introducir un telefono ingles? No"',
  'FAQs MODIF ADMIN Sec.5', 'No menciona ninguna restriccion de prefijo',
  'Si gana el compendio, el agente no se entera de la restriccion y la gestion fallara'),
 ('Monedero Solar: consecuencia de desactivar', 'ALTA',
  '000006601 Sec.9', '"Puedo desactivar el monedero solar? Si."',
  'FAQs MODIF ADMIN Sec.11', 'la modificacion se finaliza automaticamente perdiendo en ese momento el importe que hubiera en el monedero solar, es decir, quedaria a 0 EUR',
  'Perdida economica para el cliente. El procedimiento oficial omite el aviso; solo lo tiene el compendio'),
 ('Producto de precio fijo', 'ALTA',
  '000006601 Sec.1 y FAQ-CON Sec.3', 'no se podra modificar. Sera necesario esperar a la renovacion o aplicar retencion',
  'FAQs MODIF ADMIN Sec.1', 'Describe como modificar el producto sin mencionar la restriccion',
  'El compendio induce a intentar una gestion imposible'),
 ('Tipo de firma disponible', 'MEDIA',
  '000006601 Sec.7', 'electronica presencial, electronica a distancia o en papel',
  'FAQs MODIF ADMIN Sec.9', 'Tipo de firma (Distancia o Presencial)',
  'Falta la opcion papel. Nuestra pregunta B10 preguntaba exactamente por esto'),
 ('Cuenta bancaria: cuando hace falta firma', 'MEDIA',
  '000006601 Sec.6.2', 'Si no consta firmada la cuenta en el sistema, se tendra que seleccionar "Generar documento"',
  'FAQs MODIF ADMIN Sec.7', 'Pulsa "Generar documento" para la firma del cliente (siempre)',
  'Condicional frente a incondicional'),
 ('Modificaciones simultaneas', 'MEDIA',
  '000006601 Intro', 'Todas las modificaciones administrativas se pueden combinar entre ellas',
  'FAQ-CON Sec.11', 'Puedo hacer una modificacion en el contrato teniendo otra en curso? No, no es posible',
  'Se refieren a cosas distintas (combinar en la misma solicitud vs tener dos en curso) pero un agente que pregunte "puedo hacer dos a la vez" recibe respuestas opuestas'),
 ('Maximetro: terminologia de la potencia', 'BAJA',
  '000006292 Sec.3', 'la potencia debe ser la maxima del BOLETIN',
  'FAQ-CON Sec.10 y 000006590 pag.13', 'la maxima autorizada por el CIE',
  'Mismo concepto, dos terminos. Dificulta que el RAG los reconozca como equivalentes'),
]

# pasajes literales compartidos detectados (n-gramas de 5-6 palabras)
LITERALES = [
 ('6601 / FAQ-ADM', '1,2 EUR/MWh o 1,6 EUR/mes segun', 'Coste de la remesa fija. Coinciden'),
 ('6601 / FAQ-ADM', 'el contacto del punto de suministro', 'Encabezado del mismo tramite'),
 ('6601 / FAQ-ADM', 'guardar la modificacion se activa automaticamente', 'Cierre del mismo procedimiento'),
 ('6601 / FAQ-ADM', 'modificacion de datos de contacto del', 'Titulo de seccion identico'),
 ('6601 / FAQ-ADM', 'una cuenta existente desde el desplegable', 'Paso identico de cuenta bancaria'),
 ('6601 / FAQ-ADM', '1% del coste de energia', 'Coste remesa fija precio fijo'),
 ('6601 / FAQ-CON', 'que esperar a la renovacion o', 'Restriccion del producto de precio fijo'),
 ('6601 / FAQ-CON', 'si el contrato esta pendiente de firma', 'Misma casuistica de estados'),
 ('FAQ-ADM / FAQ-CON', 'la cuenta bancaria de un cliente', 'Mismo tramite'),
 ('FAQ-ADM / FAQ-CON', 'la modificacion se finaliza automaticamente', 'Mismo cierre'),
 ('6292 / 6601', 'se generara un nuevo contrato', 'Unica coincidencia entre tecnicas y administrativas'),
]

RECOMENDACION = [
 ('1', 'FUSIONAR', '000006601  +  FAQs MODIFICACIONES ADMINISTRATIVAS',
  'Son el mismo documento escrito dos veces: 11 de 12 temas duplicados y 6 contradicciones. '
  'Base de contenido: 000006601, que tiene las restricciones y avisos. '
  'Bloques "Ejemplo:" con lenguaje coloquial: del FAQ, que es lo que le hace ganar la recuperacion. '
  'Resolver antes las 6 contradicciones con negocio.'),
 ('2', 'RETIRAR', 'El que no sobreviva a la fusion',
  'Publicar el fusionado no basta: hay que despublicar el otro. Precedente: 000006590 convive '
  'con su propia version anterior bajo el mismo codigo.'),
 ('3', 'PODAR', '000006292 Modificaciones tecnicas',
  'Quitar "Datos Contrato" (el propio documento admite que es administrativa) y la mencion al '
  'Monedero Solar. Remitir al administrativo. Mismo criterio que ya se aplico al sacar los plazos '
  'de activacion de 000006590.'),
 ('4', 'DELIMITAR', '20260414 FAQs Modificaciones de contrato',
  'Su Sec.4 enumera TODAS las modificaciones, administrativas y tecnicas, lo que le hace competir '
  'con los otros tres a la vez. Dejar solo lo que es suyo: cambio de titular con modificaciones, '
  'bajas, renovacion en curso y modificacion masiva de cuenta.'),
 ('5', 'UNIFICAR', 'Terminologia CIE / boletin',
  'La regla de la potencia con maximetro aparece en 000006292, en FAQ-CON y en 000006590. '
  'Dejarla en un unico sitio y que los demas remitan.'),
]

ESTRUCTURA = [
 ('Procedimiento operativo', 'Pasos numerados + bloque FAQ al final',
  'SI, pero como complemento', 'Los pasos necesitan orden y precondiciones. Una FAQ suelta pierde '
  'la secuencia. El bloque de preguntas coloquiales al final es lo que da recuperacion.'),
 ('Referencia con datos', 'Tabla con fecha de vigencia. NO formato FAQ',
  'NO', 'Precios, potencias normalizadas, tipos impositivos. Lo que necesitan es vigencia y '
  'estructura tabular. Es el tema n.1 de fallos y ninguna FAQ lo arregla.'),
 ('Concepto o definicion', 'Definicion + No confundir con + FAQ',
  'SI', 'Aqui la FAQ encaja bien: son preguntas independientes de verdad.'),
 ('Compendio multi-tramite', 'No deberia existir',
  'NO', 'O es un indice que remite, o son fichas. Un compendio gana la recuperacion por densidad '
  'de vocabulario y desplaza al documento especifico, aunque tenga menos detalle.'),
]
