# import qrcode

# link = "upi://pay?pa=mayurvekhande14@okicici&pn=grampanchayat&tn=घरपट्टी%20भरणा&am=undefined"

# qr = qrcode.QRCode(version=1, box_size=10, border=5)
# qr.add_data(link)
# qr.make(fit=True)

# img = qr.make_image(fill='black', back_color='white')

# img.show()


import sqlite3

conn = sqlite3.connect('users.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute('UPDATE users SET akud_dey_rakam = gharpatti_ekun + divabatti_ekun + arogya_ekun')

conn.commit()
conn.close()