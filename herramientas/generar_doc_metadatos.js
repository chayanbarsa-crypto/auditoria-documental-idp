const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  LevelFormat, convertInchesToTwip
} = require('docx');
const fs = require('fs');

const NAVY = '1F3864';
const GREY = 'F2F2F2';
const W = 9638;                       // ancho util con margenes de 2 cm en A4

const cw = (...p) => {                // reparte el ancho segun pesos
  const t = p.reduce((a, b) => a + b, 0);
  const out = p.map(x => Math.floor(W * x / t));
  out[out.length - 1] += W - out.reduce((a, b) => a + b, 0);
  return out;
};

const P = (text, o = {}) => new Paragraph({
  spacing: { after: o.after === undefined ? 120 : o.after, line: 276 },
  alignment: o.align,
  children: [new TextRun({ text, bold: o.bold, italics: o.italics, size: o.size || 20,
                           color: o.color, font: 'Calibri' })]
});

const Rich = (runs, o = {}) => new Paragraph({
  spacing: { after: o.after === undefined ? 120 : o.after, line: 276 },
  children: runs.map(r => new TextRun({ text: r.t, bold: r.b, italics: r.i,
                                        size: 20, color: r.c, font: 'Calibri' }))
});

const H = (text, level) => new Paragraph({
  heading: level,
  spacing: { before: 280, after: 140 },
  children: [new TextRun({ text, bold: true, color: NAVY,
                           size: level === HeadingLevel.HEADING_1 ? 28 : 24, font: 'Calibri' })]
});

const Bullet = (text, o = {}) => new Paragraph({
  numbering: { reference: 'vinetas', level: 0 },
  spacing: { after: 80, line: 276 },
  children: [new TextRun({ text, size: 20, font: 'Calibri', bold: o.bold })]
});

const Num = (text) => new Paragraph({
  numbering: { reference: 'pasos', level: 0 },
  spacing: { after: 80, line: 276 },
  children: [new TextRun({ text, size: 20, font: 'Calibri' })]
});

const cell = (text, widths, i, o = {}) => new TableCell({
  width: { size: widths[i], type: WidthType.DXA },
  shading: o.head ? { type: ShadingType.CLEAR, fill: NAVY }
                  : (o.alt ? { type: ShadingType.CLEAR, fill: GREY } : undefined),
  margins: { top: 60, bottom: 60, left: 90, right: 90 },
  children: [new Paragraph({
    spacing: { after: 0, line: 240 },
    children: [new TextRun({ text, bold: o.head || o.bold, size: o.head ? 18 : 18,
                             color: o.head ? 'FFFFFF' : (o.color || undefined), font: 'Calibri' })]
  })]
});

const table = (headers, rows, weights) => {
  const widths = cw(...weights);
  return new Table({
    columnWidths: widths,
    width: { size: W, type: WidthType.DXA },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((h, i) => cell(h, widths, i, { head: true }))
      }),
      ...rows.map((r, n) => new TableRow({
        children: r.map((v, i) => cell(v, widths, i, { alt: n % 2 === 1, bold: i === 0 }))
      }))
    ]
  });
};

// ---------------------------------------------------------------- contenido

const IDENTIDAD = [
  ['codigo', 'Identificador unico y NO reutilizable.', 'Texto', 'Hoy 000006590 identifica a dos documentos distintos: la version antigua y la nueva conviven.'],
  ['version', 'Numero de version del documento.', '1.0, 1.1, 2.0', 'Ninguno de los 15 documentos auditados indica version. Sin esto no se sabe cual es el vigente.'],
  ['estado', 'Situacion del documento en la base.', 'VIGENTE / SUSTITUIDO / RETIRADO', 'Permite excluir de la recuperacion lo que ya no aplica sin borrarlo.'],
  ['sustituye_a', 'Codigo del documento al que reemplaza.', 'Codigo', 'Hace explicita la sustitucion. Publicar no basta: hay que marcar que el anterior deja de valer.'],
  ['fecha_publicacion', 'Fecha de alta en la base.', 'Fecha', 'Trazabilidad basica.'],
  ['fecha_ultima_revision', 'Ultima vez que se reviso el contenido.', 'Fecha', 'Ningun documento auditado la indica.'],
  ['fecha_proxima_revision', 'Cuando caduca la revision.', 'Fecha', 'Critico en precios y tarifas, que se degradan solos.'],
  ['departamento_propietario', 'Departamento que crea y mantiene el documento.', 'Lista cerrada', 'Hoy no consta. Es el dato que falta para saber a quien preguntar.'],
  ['responsable', 'Persona de contacto en ese departamento.', 'Nombre', 'Para resolver dudas y contradicciones sin buscar.'],
];

const AMBITO = [
  ['tema_canonico', 'Tema del que este documento es la fuente autorizada.', 'Lista cerrada de temas', 'Es el campo clave. Un tema, un documento canonico.'],
  ['temas_mencionados', 'Temas que toca de pasada pero NO posee.', 'Lista de temas', 'Permite que un documento mencione algo sin competir por ello en la recuperacion.'],
  ['ambito_tramite', 'Familia de gestion a la que pertenece.', 'TECNICA / ADMINISTRATIVA / CONTRATACION / BAJA / OTRA', 'Evitaria que un compendio administrativo respondiese consultas de maximetro, que es tecnica.'],
  ['regimen', 'Tipo de contrato al que aplica.', 'GENERAL / PRODUCTORES / AMBOS', 'Evitaria que documentacion de Productores respondiese consultas de contratos generales.'],
  ['producto', 'Suministro al que aplica.', 'ELECTRICIDAD / GAS / AMBOS', 'Separa procedimientos que difieren entre luz y gas.'],
  ['territorio', 'Ambito geografico, cuando aplique.', 'CCAA / PENINSULA / ISLAS / CEUTA-MELILLA / TODOS', 'Necesario en boletines, relojes horarios y tipos impositivos.'],
];

const TIPO = [
  ['tipo_documento', 'Naturaleza del contenido.', 'PROCEDIMIENTO / REFERENCIA / CONCEPTO / PLANTILLA / FORMACION / COMERCIAL', 'Permite despriorizar material formativo en consultas operativas.'],
  ['audiencia', 'A quien va dirigido.', 'AGENTE / CLIENTE / INTERNO', 'Evita servir documentacion interna o comercial a una consulta operativa.'],
  ['vigencia', 'Si el contenido caduca por si solo.', 'PERMANENTE / PERIODICA', 'Marca los que necesitan mantenimiento con calendario, como los precios.'],
];

const doc = new Document({
  creator: 'Auditoria documental LucIA',
  title: 'Metadatos de ambito para la base documental de LucIA',
  numbering: {
    config: [
      { reference: 'vinetas', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
      { reference: 'pasos', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
    ]
  },
  sections: [{
    properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    children: [

      new Paragraph({
        spacing: { after: 60 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: NAVY, space: 8 } },
        children: [new TextRun({ text: 'Metadatos de ambito para la base documental de LucIA',
                                 bold: true, size: 34, color: NAVY, font: 'Calibri' })]
      }),
      P('Propuesta para resolver el solapamiento entre documentos sin fusionarlos ni retirar la propiedad a ningun departamento.',
        { italics: true, color: '595959', after: 320 }),

      H('1. Para que es este documento', HeadingLevel.HEADING_1),
      P('Cuatro documentos sobre modificaciones de contrato, creados por departamentos distintos, cubren el mismo territorio y compiten entre si cuando LucIA busca una respuesta. El analisis de solapamiento detecto 26 temas, de los que 18 aparecen en dos o mas documentos y 9 en tres o mas.'),
      P('La salida evidente seria fusionarlos en uno solo. No es viable: obligaria a varios departamentos a ceder la propiedad de su documento y a acordar un mantenedor unico, y cada cambio posterior necesitaria el visto bueno de todos.'),
      P('Este documento describe la alternativa: dejar los documentos donde estan y darle al sistema la informacion que necesita para saber cual es el competente en cada tema.'),

      H('2. El problema, en una frase', HeadingLevel.HEADING_1),
      Rich([{ t: 'LucIA recupera por parecido semantico, no por competencia organizativa. ', b: true },
            { t: 'No sabe que departamento es el dueno de cada tema, porque esa informacion no existe en ninguna parte de la base documental.' }]),
      P('El solapamiento no es un fallo de los departamentos: cada uno escribio un documento correcto para su ambito. El problema aparece cuando un buscador que solo entiende de parecido textual tiene que elegir entre cuatro documentos parecidos.'),

      H('3. Lo que ya esta medido', HeadingLevel.HEADING_1),
      P('Estos casos se han observado en pruebas y en trafico real, y todos se resolverian con metadatos:'),
      Bullet('Un compendio de modificaciones ADMINISTRATIVAS gana consultas sobre maximetro, que es una modificacion TECNICA. El documento que gana no contiene la respuesta.'),
      Bullet('Documentacion del regimen de PRODUCTORES responde consultas sobre contratos generales, porque el nombre y el contenido se parecen mucho.'),
      Bullet('Consultas sobre precios vigentes se responden desde un curso de formacion de junio, con riesgo de trasladar precios caducados a un cliente.'),
      Bullet('Un documento actualizado convive con su propia version anterior bajo el mismo codigo, porque publicar no retira lo anterior.'),

H('4. Accion inmediata: eliminar las contradicciones', HeadingLevel.HEADING_1),

      Rich([{ t: 'El problema no es que dos documentos hablen del mismo tema. Es que digan cosas distintas.', b: true }]),
      P('Si dos departamentos escriben sobre el Monedero Solar y ambos dicen lo mismo, da igual cual de los dos recupere LucIA: el agente recibe una respuesta correcta. Se pierde precision, no se pierde correccion.'),
      P('El dano aparece cuando se contradicen. Entonces la respuesta que recibe el agente depende de cual gane la busqueda ese dia, y eso es una loteria. En el analisis de los cuatro documentos de modificaciones se han detectado ocho contradicciones, cuatro de ellas de riesgo alto.'),
      Rich([{ t: 'Lo importante: corregir una contradiccion es casi siempre anadir o cambiar una frase, no reescribir un documento. ', b: true },
            { t: 'Cada departamento toca solo las dos o tres que le afectan, y nadie tiene que ceder la propiedad de nada.' }]),

      H('4.1  Tres ejemplos reales', HeadingLevel.HEADING_2),

      Rich([{ t: 'Ejemplo 1. Dos pasos opuestos.', b: true }], { after: 60 }),
      Bullet('Un documento dice: rellena la direccion, pulsa "Normalizar" y despues "Guardar".'),
      Bullet('El otro dice: rellena la direccion y pulsa "Guardar sin normalizar".'),
      P('El agente hara una cosa u otra segun cual le sirva LucIA. Uno de los dos esta mal. Arreglo: negocio decide cual es el bueno y se corrige el otro. Es cambiar una linea.', { after: 200 }),

      Rich([{ t: 'Ejemplo 2. Un aviso que solo esta en un sitio.', b: true }], { after: 60 }),
      Bullet('Un documento dice: "Puedo desactivar el monedero solar? Si."'),
      Bullet('El otro anade: al desactivarlo se pierde el importe acumulado, que queda a cero.'),
      P('Si LucIA responde con el primero, el agente desactiva el servicio y el cliente pierde su saldo sin que nadie le avisara. Arreglo: copiar la advertencia al documento que no la tiene. Es anadir una frase.', { after: 200 }),

      Rich([{ t: 'Ejemplo 3. Una restriccion que se omite.', b: true }], { after: 60 }),
      Bullet('Un documento dice: es obligatorio un numero de movil espanol.'),
      Bullet('El otro describe el mismo tramite sin mencionar la restriccion.'),
      P('El agente introduce un telefono extranjero y la gestion falla. Arreglo: anadir la restriccion al documento que la omite.', { after: 200 }),

      H('4.2  Como se ejecuta', HeadingLevel.HEADING_2),
      Num('Repartir las ocho contradicciones por departamento propietario.'),
      Num('Cada departamento decide, sobre las suyas, cual es la version correcta.'),
      Num('Se corrige el documento equivocado o se copia el aviso que falta.'),
      Num('Se relanzan las preguntas de prueba afectadas para comprobar que la respuesta ya no depende de cual gane la busqueda.'),
      P('Es la unica accion de esta propuesta que puede empezar hoy, sin depender de la plataforma ni de ningun acuerdo de propiedad.'),

      H('5. La solucion de fondo: que el sistema sepa a quien preguntar', HeadingLevel.HEADING_1),
      P('Eliminar las contradicciones quita el riesgo, pero no quita el solapamiento: LucIA seguira eligiendo entre cuatro documentos parecidos, y seguira acertando por casualidad. Para eso hace falta lo que viene a continuacion.'),

      H('6. Que son los metadatos de ambito', HeadingLevel.HEADING_1),
      P('Son etiquetas que acompanan a cada documento y describen a que aplica y quien lo mantiene. No forman parte del texto: son datos sobre el documento, no contenido para el agente.'),
      P('Con ellos, la busqueda deja de ser unicamente "que texto se parece mas a la pregunta" y pasa a ser "que texto se parece mas, entre los documentos que aplican a este caso y estan vigentes".'),
      Rich([{ t: 'Ventaja principal: no se toca ni una linea de contenido. ', b: true },
            { t: 'Ningun departamento pierde su documento ni tiene que reescribirlo. Solo tiene que declarar de que va.' }]),

      H('7. Campos propuestos', HeadingLevel.HEADING_1),

      H('7.1  Identidad y trazabilidad', HeadingLevel.HEADING_2),
      P('Responden a: que documento es este, quien lo mantiene y si sigue valiendo. Hoy no existe ninguno de ellos.', { italics: true, color: '595959' }),
      table(['Campo', 'Que es', 'Valores', 'Por que hace falta'], IDENTIDAD, [1.6, 2.4, 2.0, 3.4]),

      new Paragraph({ spacing: { after: 200 }, children: [] }),

      H('7.2  Ambito de aplicacion', HeadingLevel.HEADING_2),
      P('Responden a: a que casos aplica este documento. Son los que resuelven el solapamiento.', { italics: true, color: '595959' }),
      table(['Campo', 'Que es', 'Valores', 'Por que hace falta'], AMBITO, [1.6, 2.4, 2.0, 3.4]),

      new Paragraph({ spacing: { after: 200 }, children: [] }),

      H('7.3  Tipo y uso', HeadingLevel.HEADING_2),
      P('Responden a: que clase de documento es y a quien sirve.', { italics: true, color: '595959' }),
      table(['Campo', 'Que es', 'Valores', 'Por que hace falta'], TIPO, [1.6, 2.4, 2.0, 3.4]),

      H('8. El mecanismo: canonico frente a mencionado', HeadingLevel.HEADING_1),
      P('De todos los campos, el que resuelve el problema de fondo es la pareja tema_canonico / temas_mencionados.'),
      P('Cada tema tiene un unico documento canonico: el que manda. Los demas pueden mencionarlo, pero lo declaran como tema mencionado, no como propio. En la recuperacion, un documento solo compite por los temas que posee.'),
      Rich([{ t: 'Ejemplo. ', b: true },
            { t: 'El Monedero Solar aparece hoy en cuatro documentos. Con metadatos, uno lo declara como tema_canonico y los otros tres como tema mencionado. Una consulta sobre Monedero Solar va siempre al primero. Los otros tres siguen mencionandolo para dar contexto, pero dejan de competir.' }]),
      P('Esto es lo que se queria decir con que el sistema sepa a quien preguntar: no es que el buscador adivine mejor, es que la base documental declara quien es el competente.'),

      H('9. Como se desarrollaria', HeadingLevel.HEADING_1),
      Num('Comprobar que la plataforma admite filtrado por metadatos. Es la pregunta que condiciona todo lo demas y deberia responderla quien administra el buscador. Si la respuesta es no, ver el apartado 11.'),
      Num('Levantar el inventario. Un Excel con los documentos de la base y los campos de este documento. Es el paso pendiente descrito en el apartado 12.'),
      Num('Etiquetar. Cada departamento rellena los campos de sus documentos. Nadie etiqueta los de otro.'),
      Num('Resolver los conflictos de tema canonico. Donde dos departamentos reclamen el mismo tema, hay que decidir. Son pocos casos y es la unica conversacion incomoda del proceso.'),
      Num('Configurar el filtrado y medir. Relanzar las pruebas ya existentes y comparar contra la linea base para ver si la recuperacion mejora.'),
      Num('Fijar la regla de publicacion: ningun documento entra en la base sin metadatos completos, y publicar una version nueva obliga a marcar la anterior como SUSTITUIDO.'),

      H('10. Que se le pide a cada departamento', HeadingLevel.HEADING_1),
      P('El encargo es corto y no implica reescribir nada:'),
      Bullet('Declarar los metadatos de cada documento propio.'),
      Bullet('Declarar solo como canonicos los temas de los que se es responsable. El resto, como mencionados.'),
      Bullet('Antes de crear un documento nuevo, comprobar si el tema ya tiene dueno. Si lo tiene, se amplia el suyo; no se crea otro.'),
      Bullet('Al publicar una version nueva, marcar la anterior como SUSTITUIDO e indicar el codigo que la reemplaza.'),
      Bullet('Si el documento contiene datos que caducan, fijar fecha de proxima revision.'),

      H('11. Si la plataforma no admite filtrado', HeadingLevel.HEADING_1),
      P('Existe una alternativa mas debil pero que no depende de nadie: incluir los mismos campos como cabecera visible en la primera pagina del documento.'),
      P('No permite filtrar de verdad, pero el texto de la cabecera entra en el indice, de modo que una consulta sobre Productores tiene mas probabilidad de encontrar el documento que lo declara. Y ademas cubre una carencia ya detectada en la auditoria: ninguno de los documentos revisados incluye cabecera de metadatos.'),
      P('Es la opcion de reserva, no la recomendada.'),

      H('12. Pendiente: Excel de trazabilidad', HeadingLevel.HEADING_1),
      Rich([{ t: 'Queda pendiente elaborar un Excel de trazabilidad de los documentos de la base, ', b: true },
            { t: 'con una fila por documento y una columna por cada campo descrito en el apartado 7.' }]),
      P('Ese inventario es el paso 2 del desarrollo y cumple tres funciones a la vez:'),
      Bullet('Es el formulario donde cada departamento declara sus metadatos.'),
      Bullet('Es la fuente desde la que se cargaria el filtrado en la plataforma.'),
      Bullet('Es donde se ven los conflictos: dos documentos que reclaman el mismo tema canonico aparecen uno al lado del otro.'),
      P('Mientras no exista, no se puede saber cuantos temas estan duplicados en el conjunto de la base ni cuantos documentos siguen vigentes.'),
    ]
  }]
});

Packer.toBuffer(doc).then(b => {
  fs.writeFileSync(require('path').join(__dirname,'..','metadatos_ambito_LucIA.docx'), b);
  console.log('OK -> metadatos_ambito_LucIA.docx  (' + b.length + ' bytes)');
});
