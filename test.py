import qrcode

link = "upi://pay?pa=mayurvekhande14@okicici&pn=grampanchayat&tn=घरपट्टी%20भरणा&am=undefined"

qr = qrcode.QRCode(version=1, box_size=10, border=5)
qr.add_data(link)
qr.make(fit=True)

img = qr.make_image(fill='black', back_color='white')

img.show()