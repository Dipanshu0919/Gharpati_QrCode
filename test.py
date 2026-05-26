import sqlite3
import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta

Indiantime = datetime.datetime.now() + timedelta(hours=5, minutes=30)

conn = sqlite3.connect('users.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()


c.execute('SELECT * FROM users')
users = c.fetchall()

# show users with payment status "Paid" 

# 1. Current till month range

month_range = int(input("Enter month range from now to show from that range till now: "))

for user in users:
    status = user['payment_status']
    if status and status.startswith("Paid"):
        sp = status.split("Paid ")[1]
        try:
            payment_date = datetime.datetime.strptime(sp, "%Y-%m-%d %H:%M:%S.%f")

            if payment_date >= Indiantime - relativedelta(months=month_range):
                print(f"User: {user['midkatkram']}, Payment Status: {status}")
        except ValueError:
            print(f"User: {user['midkatkram']}, Payment Status: {status} (Invalid date format)")


# 2. particular month range

month_range = int(input("Enter month to check (1-12): "))

for user in users:
    status = user['payment_status']
    if status and status.startswith("Paid"):
        sp = status.split("Paid ")[1]
        try:
            payment_date = datetime.datetime.strptime(sp, "%Y-%m-%d %H:%M:%S.%f")
            if payment_date.month == month_range:
                print(f"User: {user['midkatkram']}, Payment Status: {status}")
        except ValueError:
            print(f"User: {user['midkatkram']}, Payment Status: {status} (Invalid date format)")

# 3. from month range to month range

start_month = int(input("Enter start month to check (1-12): "))
end_month = int(input("Enter end month to check (1-12): "))

for user in users:
    status = user['payment_status']
    if status and status.startswith("Paid"):
        sp = status.split("Paid ")[1]
        try:
            payment_date = datetime.datetime.strptime(sp, "%Y-%m-%d %H:%M:%S.%f")
            if (
                (start_month <= end_month and start_month <= payment_date.month <= end_month)
                or
                (start_month > end_month and (payment_date.month >= start_month or payment_date.month <= end_month))
            ):                
                print(f"User: {user['midkatkram']}, Payment Status: {status}")
        except ValueError:
            print(f"User: {user['midkatkram']}, Payment Status: {status} (Invalid date format)")


conn.commit()
conn.close()