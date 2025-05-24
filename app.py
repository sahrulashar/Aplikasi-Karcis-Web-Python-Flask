from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from datetime import datetime
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'karcis_secret'

# Koneksi ke database
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='karcis_db'
    )

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login berhasil!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah.', 'danger')

    return render_template('login.html')

# Dashboard
from datetime import datetime, date

from datetime import datetime

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Pendapatan hari ini
    cursor.execute("SELECT SUM(subtotal) AS total FROM transaksi WHERE DATE(waktu) = CURDATE()")
    total_hari_ini = cursor.fetchone()['total'] or 0

    # Pengunjung hari ini
    cursor.execute("SELECT SUM(jumlah) AS total FROM transaksi WHERE DATE(waktu) = CURDATE()")
    total_pengunjung = cursor.fetchone()['total'] or 0

    # Pendapatan per hari bulan ini untuk grafik harian
    cursor.execute("""
        SELECT DATE(waktu) as tanggal, SUM(subtotal) AS total 
        FROM transaksi 
        WHERE MONTH(waktu) = MONTH(CURDATE()) AND YEAR(waktu) = YEAR(CURDATE())
        GROUP BY DATE(waktu)
        ORDER BY DATE(waktu)
    """)
    rows = cursor.fetchall()

    if not rows:
        labels = ['01', '02', '03']
        data = [0, 0, 0]
    else:
        try:
            labels = [datetime.strptime(row['tanggal'], '%Y-%m-%d').strftime('%d %b') for row in rows]
        except Exception:
            labels = [row['tanggal'].strftime('%d %b') for row in rows]
        data = [row['total'] for row in rows]

    # --- Data Pendapatan Bulanan (12 bulan terakhir) ---
    cursor.execute("""
        SELECT DATE_FORMAT(waktu, '%Y-%m') AS bulan, SUM(subtotal) AS total
        FROM transaksi
        WHERE waktu >= DATE_SUB(CURDATE(), INTERVAL 11 MONTH)
        GROUP BY bulan
        ORDER BY bulan
    """)
    rows_bulan = cursor.fetchall()
    pendapatan_per_bulan = {row['bulan']: row['total'] for row in rows_bulan}

    now = datetime.now()
    labels_bulanan = []
    data_bulanan = []
    for i in range(11, -1, -1):
        bulan_iter = (now.month - i - 1) % 12 + 1
        tahun_iter = now.year - ((now.month - i - 1) // 12)
        key = f"{tahun_iter}-{bulan_iter:02d}"
        labels_bulanan.append(datetime(year=tahun_iter, month=bulan_iter, day=1).strftime('%b %Y'))
        data_bulanan.append(pendapatan_per_bulan.get(key, 0))
    key_bulan_ini = now.strftime('%Y-%m')
    total_bulan_ini = pendapatan_per_bulan.get(key_bulan_ini, 0)

    # --- Data Pendapatan Mingguan (7 hari terakhir) ---
    # Ambil tanggal 7 hari terakhir
    tanggal_sekarang = now.date()
    tanggal_7_hari_lalu = tanggal_sekarang - timedelta(days=6)

    cursor.execute("""
        SELECT DATE(waktu) as tanggal, SUM(subtotal) AS total
        FROM transaksi
        WHERE DATE(waktu) BETWEEN %s AND %s
        GROUP BY DATE(waktu)
        ORDER BY DATE(waktu)
    """, (tanggal_7_hari_lalu, tanggal_sekarang))
    rows_mingguan = cursor.fetchall()

    # Buat dict tanggal -> total pendapatan
    pendapatan_per_hari_mingguan = {row['tanggal'].strftime('%Y-%m-%d') if hasattr(row['tanggal'], 'strftime') else row['tanggal']: row['total'] for row in rows_mingguan}

    labels_mingguan = []
    data_mingguan = []
    for i in range(6, -1, -1):
        day = tanggal_sekarang - timedelta(days=i)
        labels_mingguan.append(day.strftime('%a %d %b'))
        key = day.strftime('%Y-%m-%d')
        data_mingguan.append(pendapatan_per_hari_mingguan.get(key, 0))

    # Total pendapatan minggu ini
    total_mingguan = sum(data_mingguan)

    cursor.close()
    db.close()

    return render_template('dashboard.html',
                           total_hari_ini=total_hari_ini,
                           total_bulan_ini=total_bulan_ini,
                           total_pengunjung=total_pengunjung,
                           total_mingguan=total_mingguan,
                           chart_labels=labels,
                           chart_data=data,
                           chart_labels_bulanan=labels_bulanan,
                           chart_data_bulanan=data_bulanan,
                           chart_labels_mingguan=labels_mingguan,
                           chart_data_mingguan=data_mingguan,
                           bulan_ini=now.strftime('%B'),
                           tahun_ini=now.strftime('%Y'))

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))

# Harga tiket
tickets = {
    'Dewasa': 10000,
    'Anak-anak': 10000,
    'Lansia': 15000
}

# Penjualan karcis
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        waktu = datetime.now()
        db = get_db_connection()
        cursor = db.cursor()

        transaksi_ids = []
        total = 0

        for ticket, price in tickets.items():
            jumlah = int(request.form.get(ticket, 0))
            subtotal = jumlah * price
            total += subtotal

            if jumlah > 0:
                cursor.execute(
                    "INSERT INTO transaksi (waktu, tiket, jumlah, subtotal) VALUES (%s, %s, %s, %s)",
                    (waktu, ticket, jumlah, subtotal)
                )
                transaksi_ids.append(cursor.lastrowid)

        db.commit()
        cursor.close()
        db.close()

        if transaksi_ids:
            session['transaksi_ids'] = transaksi_ids
            nomor_karcis = datetime.now().strftime('%Y%m%d') + '-' + str(transaksi_ids[0]).zfill(4)
            session['nomor_karcis'] = nomor_karcis

        return redirect(url_for('print_ticket'))

    return render_template('index.html', tickets=tickets, total=None)

# Cetak karcis
# Cetak karcis
@app.route('/print_ticket')
def print_ticket():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    transaksi_ids = session.get('transaksi_ids', [])
    nomor_karcis = session.get('nomor_karcis')

    if not transaksi_ids:
        flash('Data transaksi tidak ditemukan.', 'danger')
        return redirect(url_for('index'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    format_strings = ','.join(['%s'] * len(transaksi_ids))
    query = f"SELECT * FROM transaksi WHERE id IN ({format_strings}) ORDER BY id"
    cursor.execute(query, transaksi_ids)
    data = cursor.fetchall()

    total = sum(item['subtotal'] for item in data)
    waktu = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

    cursor.close()
    db.close()

    # Panggil fungsi terbilang
    terbilang_total = terbilang(total)

    return render_template('print_ticket.html', data=data, nomor_karcis=nomor_karcis, waktu=waktu, total=total, terbilang_total=terbilang_total)


# Lihat semua transaksi
@app.route('/transaksi')
def lihat_transaksi():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM transaksi ORDER BY waktu DESC")
    data = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('transaksi.html', data=data)

def terbilang(n):
    angka = ["", "Satu", "Dua", "Tiga", "Empat", "Lima",
             "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]

    def _to_words(x):
        x = int(x)
        if x < 12:
            return angka[x]
        elif x < 20:
            return _to_words(x - 10) + " Belas"
        elif x < 100:
            return _to_words(x // 10) + " Puluh " + _to_words(x % 10)
        elif x < 200:
            return "Seratus " + _to_words(x - 100)
        elif x < 1000:
            return _to_words(x // 100) + " Ratus " + _to_words(x % 100)
        elif x < 2000:
            return "Seribu " + _to_words(x - 1000)
        elif x < 1000000:
            return _to_words(x // 1000) + " Ribu " + _to_words(x % 1000)
        elif x < 1000000000:
            return _to_words(x // 1000000) + " Juta " + _to_words(x % 1000000)
        elif x < 1000000000000:
            return _to_words(x // 1000000000) + " Milyar " + _to_words(x % 1000000000)
        else:
            return "Angka terlalu besar"

    result = _to_words(n).strip()
    # Perbaiki spasi ganda dan hilangkan spasi di akhir
    while "  " in result:
        result = result.replace("  ", " ")
    return result if result != "" else "Nol"


if __name__ == '__main__':
    app.run(debug=True)
