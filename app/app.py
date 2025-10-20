from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO
import sqlite3
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Inicializar base de datos
def init_db():
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    
    # Tabla de productos
    c.execute('''CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        descripcion TEXT,
        precio REAL NOT NULL,
        stock INTEGER NOT NULL,
        imagen TEXT
    )''')
    
    # Tabla de pedidos
    c.execute('''CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_orden TEXT UNIQUE NOT NULL,
        cliente_nombre TEXT NOT NULL,
        cliente_telefono TEXT NOT NULL,
        cliente_direccion TEXT NOT NULL,
        metodo_pago TEXT NOT NULL,
        total REAL NOT NULL,
        estado TEXT DEFAULT 'pendiente',
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tabla de detalle de pedidos
    c.execute('''CREATE TABLE IF NOT EXISTS detalle_pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        producto_nombre TEXT NOT NULL,
        cantidad INTEGER NOT NULL,
        precio_unitario REAL NOT NULL,
        subtotal REAL NOT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )''')
    
    # Tabla de facturas
    c.execute('''CREATE TABLE IF NOT EXISTS facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        numero_factura TEXT UNIQUE NOT NULL,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
    )''')
    
    # Tabla de administradores
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')
    
    # Insertar admin por defecto (usuario: admin, password: admin123)
    c.execute("INSERT OR IGNORE INTO admin (usuario, password) VALUES (?, ?)", 
              ('admin', 'admin123'))
    
    # Insertar productos de ejemplo si no existen
    c.execute("SELECT COUNT(*) FROM productos")
    if c.fetchone()[0] == 0:
        productos_ejemplo = [
            ('Pechuga de Pollo', 'Pechuga fresca sin hueso', 15000, 50, 'pechuga.jpg'),
            ('Alas de Pollo', 'Alas frescas (paquete de 1kg)', 12000, 30, 'alas.jpg'),
            ('Piernas de Pollo', 'Piernas frescas (paquete de 1kg)', 13000, 40, 'piernas.jpg'),
            ('Pollo Entero', 'Pollo entero fresco', 25000, 20, 'pollo_entero.jpg'),
            ('Muslos de Pollo', 'Muslos frescos (paquete de 1kg)', 14000, 35, 'muslos.jpg'),
            ('Filete de Pechuga', 'Filete de pechuga marinado', 18000, 25, 'filete.jpg')
        ]
        c.executemany("INSERT INTO productos (nombre, descripcion, precio, stock, imagen) VALUES (?, ?, ?, ?, ?)", 
                     productos_ejemplo)
    
    conn.commit()
    conn.close()

# Ruta principal - Catálogo de productos con búsqueda
@app.route('/')
def index():
    busqueda = request.args.get('buscar', '').strip()
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    
    if busqueda:
        # Buscar en nombre o descripción (case insensitive)
        query = """SELECT * FROM productos 
                   WHERE stock > 0 
                   AND (LOWER(nombre) LIKE LOWER(?) OR LOWER(descripcion) LIKE LOWER(?))"""
        c.execute(query, (f'%{busqueda}%', f'%{busqueda}%'))
    else:
        c.execute("SELECT * FROM productos WHERE stock > 0")
    
    productos = c.fetchall()
    conn.close()
    
    return render_template('index.html', productos=productos, busqueda=busqueda)

# Agregar al carrito
@app.route('/agregar_carrito/<int:producto_id>', methods=['POST'])
def agregar_carrito(producto_id):
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    producto = c.fetchone()
    conn.close()
    
    if producto and producto[4] > 0:  # Verificar stock
        if 'carrito' not in session:
            session['carrito'] = []
        
        carrito = session['carrito']
        encontrado = False
        
        for item in carrito:
            if item['id'] == producto_id:
                if item['cantidad'] < producto[4]:  # Verificar stock disponible
                    item['cantidad'] += 1
                encontrado = True
                break
        
        if not encontrado:
            carrito.append({
                'id': producto[0],
                'nombre': producto[1],
                'precio': producto[3],
                'cantidad': 1,
                'stock': producto[4]
            })
        
        session['carrito'] = carrito
        session.modified = True
    
    return redirect(url_for('index'))

# Ver carrito
@app.route('/carrito')
def carrito():
    carrito = session.get('carrito', [])
    total = sum(item['precio'] * item['cantidad'] for item in carrito)
    return render_template('carrito.html', carrito=carrito, total=total)

# Actualizar cantidad en carrito
@app.route('/actualizar_carrito/<int:producto_id>', methods=['POST'])
def actualizar_carrito(producto_id):
    cantidad = int(request.form.get('cantidad', 1))
    carrito = session.get('carrito', [])
    
    for item in carrito:
        if item['id'] == producto_id:
            if cantidad > 0 and cantidad <= item['stock']:
                item['cantidad'] = cantidad
            elif cantidad <= 0:
                carrito.remove(item)
            break
    
    session['carrito'] = carrito
    session.modified = True
    return redirect(url_for('carrito'))

# Eliminar del carrito
@app.route('/eliminar_carrito/<int:producto_id>')
def eliminar_carrito(producto_id):
    carrito = session.get('carrito', [])
    session['carrito'] = [item for item in carrito if item['id'] != producto_id]
    session.modified = True
    return redirect(url_for('carrito'))

# Checkout
@app.route('/checkout')
def checkout():
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('index'))
    total = sum(item['precio'] * item['cantidad'] for item in carrito)
    return render_template('checkout.html', carrito=carrito, total=total)

# Procesar pedido
@app.route('/procesar_pedido', methods=['POST'])
def procesar_pedido():
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('index'))
    
    nombre = request.form.get('nombre')
    telefono = request.form.get('telefono')
    direccion = request.form.get('direccion')
    metodo_pago = request.form.get('metodo_pago')
    
    total = sum(item['precio'] * item['cantidad'] for item in carrito)
    numero_orden = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    numero_factura = f"FAC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    
    # Crear pedido
    c.execute('''INSERT INTO pedidos (numero_orden, cliente_nombre, cliente_telefono, 
                 cliente_direccion, metodo_pago, total) VALUES (?, ?, ?, ?, ?, ?)''',
              (numero_orden, nombre, telefono, direccion, metodo_pago, total))
    pedido_id = c.lastrowid
    
    # Agregar detalle del pedido y actualizar stock
    for item in carrito:
        c.execute('''INSERT INTO detalle_pedidos (pedido_id, producto_id, producto_nombre, 
                     cantidad, precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?, ?)''',
                  (pedido_id, item['id'], item['nombre'], item['cantidad'], 
                   item['precio'], item['precio'] * item['cantidad']))
        
        # Actualizar stock
        c.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", 
                  (item['cantidad'], item['id']))
    
    # Crear factura
    c.execute("INSERT INTO facturas (pedido_id, numero_factura) VALUES (?, ?)",
              (pedido_id, numero_factura))
    
    conn.commit()
    conn.close()
    
    # Limpiar carrito
    session['carrito'] = []
    session.modified = True
    
    return redirect(url_for('confirmacion', numero_orden=numero_orden))

# Confirmación de pedido
@app.route('/confirmacion/<numero_orden>')
def confirmacion(numero_orden):
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    
    c.execute('''SELECT p.*, f.numero_factura FROM pedidos p 
                 JOIN facturas f ON p.id = f.pedido_id 
                 WHERE p.numero_orden = ?''', (numero_orden,))
    pedido = c.fetchone()
    
    c.execute('''SELECT * FROM detalle_pedidos WHERE pedido_id = ?''', (pedido[0],))
    detalle = c.fetchall()
    
    conn.close()
    return render_template('confirmacion.html', pedido=pedido, detalle=detalle)

# Login administrador
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        
        conn = sqlite3.connect('polleria.db')
        c = conn.cursor()
        c.execute("SELECT * FROM admin WHERE usuario = ? AND password = ?", 
                  (usuario, password))
        admin = c.fetchone()
        conn.close()
        
        if admin:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Credenciales incorrectas")
    
    return render_template('admin_login.html')

# Dashboard administrador
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')

# Gestión de productos
@app.route('/admin/productos')
def admin_productos():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute("SELECT * FROM productos")
    productos = c.fetchall()
    conn.close()
    return render_template('admin_productos.html', productos=productos)

# Agregar producto
@app.route('/admin/productos/agregar', methods=['GET', 'POST'])
def admin_agregar_producto():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio = float(request.form.get('precio'))
        stock = int(request.form.get('stock'))
        imagen = request.form.get('imagen', 'default.jpg')
        
        conn = sqlite3.connect('polleria.db')
        c = conn.cursor()
        c.execute('''INSERT INTO productos (nombre, descripcion, precio, stock, imagen) 
                     VALUES (?, ?, ?, ?, ?)''', (nombre, descripcion, precio, stock, imagen))
        conn.commit()
        conn.close()
        
        return redirect(url_for('admin_productos'))
    
    return render_template('admin_agregar_producto.html')

# Editar producto
@app.route('/admin/productos/editar/<int:producto_id>', methods=['GET', 'POST'])
def admin_editar_producto(producto_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio = float(request.form.get('precio'))
        stock = int(request.form.get('stock'))
        imagen = request.form.get('imagen')
        
        c.execute('''UPDATE productos SET nombre=?, descripcion=?, precio=?, stock=?, imagen=? 
                     WHERE id=?''', (nombre, descripcion, precio, stock, imagen, producto_id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_productos'))
    
    c.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
    producto = c.fetchone()
    conn.close()
    return render_template('admin_editar_producto.html', producto=producto)

# Eliminar producto
@app.route('/admin/productos/eliminar/<int:producto_id>')
def admin_eliminar_producto(producto_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_productos'))

# Ver pedidos
@app.route('/admin/pedidos')
def admin_pedidos():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute("SELECT * FROM pedidos ORDER BY fecha DESC")
    pedidos = c.fetchall()
    conn.close()
    return render_template('admin_pedidos.html', pedidos=pedidos)

# Ver detalle de pedido
@app.route('/admin/pedidos/<int:pedido_id>')
def admin_detalle_pedido(pedido_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,))
    pedido = c.fetchone()
    c.execute("SELECT * FROM detalle_pedidos WHERE pedido_id = ?", (pedido_id,))
    detalle = c.fetchall()
    conn.close()
    return render_template('admin_detalle_pedido.html', pedido=pedido, detalle=detalle)

# Ver facturas
@app.route('/admin/facturas')
def admin_facturas():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute('''SELECT f.*, p.numero_orden, p.cliente_nombre, p.total 
                 FROM facturas f 
                 JOIN pedidos p ON f.pedido_id = p.id 
                 ORDER BY f.fecha DESC''')
    facturas = c.fetchall()
    conn.close()
    return render_template('admin_facturas.html', facturas=facturas)

# Logout admin
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

# Descargar reporte de facturas en PDF
@app.route('/admin/facturas/descargar_pdf')
def admin_descargar_pdf_facturas():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    # Crear buffer de memoria para el PDF
    buffer = BytesIO()
    
    # Crear el PDF
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Estilos
    styles = getSampleStyleSheet()
    
    # Título
    title = Paragraph("<b>Don Pollo</b>", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    subtitle = Paragraph(f"<b>Reporte de Facturas</b><br/>Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Heading2'])
    elements.append(subtitle)
    elements.append(Spacer(1, 0.3*inch))
    
    # Obtener datos de facturas
    conn = sqlite3.connect('polleria.db')
    c = conn.cursor()
    c.execute('''SELECT f.numero_factura, p.numero_orden, p.cliente_nombre, p.total, f.fecha 
                 FROM facturas f 
                 JOIN pedidos p ON f.pedido_id = p.id 
                 ORDER BY f.fecha DESC''')
    facturas = c.fetchall()
    conn.close()
    
    if facturas:
        # Crear tabla
        data = [['Nro. Factura', 'Nro. Orden', 'Cliente', 'Total', 'Fecha']]
        
        total_general = 0
        for factura in facturas:
            data.append([
                factura[0],
                factura[1],
                factura[2],
                f"${factura[3]:,.0f}",
                factura[4]
            ])
            total_general += factura[3]
        
        # Agregar fila de total
        data.append(['', '', 'TOTAL GENERAL:', f"${total_general:,.0f}", ''])
        
        # Crear y estilizar tabla
        table = Table(data, colWidths=[2*inch, 2*inch, 2*inch, 1.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FF6B35')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8f9fa')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))
        
        # Resumen
        resumen = Paragraph(f"<b>Total de facturas:</b> {len(facturas)}", styles['Normal'])
        elements.append(resumen)
    else:
        no_data = Paragraph("No hay facturas registradas en el sistema.", styles['Normal'])
        elements.append(no_data)
    
    # Generar PDF
    doc.build(elements)
    
    # Preparar respuesta
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=reporte_facturas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    
    return response

if __name__ == '__main__':
    init_db()
    app.run(debug=True)