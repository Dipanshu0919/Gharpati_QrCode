# Gharpati QR Code System

A specialized management platform designed for local village administrations (Gram Panchayats) to digitize property tax collection and civil service requests using QR-based automation.

## 🎯 Purpose

The system serves two primary functions:

1. **Tax Management**: Automates the generation of QR-coded tax cards that citizens can scan to view their outstanding dues (Property Tax, Lighting, Health, etc.) and make UPI payments
2. **Civil Services**: Provides a digital interface for citizens to request official documents such as Birth Certificates, Death Certificates, and Marriage Certificates

## 👥 Target Users

- **Administrators**: Gram Panchayat officials who manage tax records via CSV uploads, approve payments, and process certificate requests
- **Citizens**: Property owners who use generated QR codes to access their personalized tax dashboards and submit payment proofs

## 🛠️ Technology Stack

- **Backend**: Flask (Python)
- **Database**: SQLite for persistent storage of users, admins, and service requests 
- **Image Processing**: Pillow (PIL) and `qrcode` for generating multilingual tax cards and payment URIs 
- **Frontend**: Jinja2 templates with responsive CSS and `html2pdf.js` for receipt generation

## 📋 Features

### Tax Management
- Bulk CSV upload for property tax records with automatic financial calculations
- QR code generation for tax cards (both URL and UPI payment codes)
- Multi-language support (Marathi/English) for tax cards
- Payment screenshot upload and verification workflow
- Digital receipt generation for approved payments

### Civil Services
- Online application forms for Birth, Death, and Marriage certificates
- Admin dashboard for processing certificate requests
- Status tracking for service requests

### Administrative Tools
- Admin authentication and session management
- Dashboard with search, filter, and pagination for user records
- Payment verification workflow (Pending → Paid → Approved)
- Statistics and reporting with export functionality
- CRUD operations for individual tax records

## 🗄️ Database Schema

The system uses SQLite with three main tables:

### Users Table
Stores property tax records with fields for:
- Property identification (`midkatkram`, `ghar_malkache_nav`)
- Tax breakdowns (`gharpatti_*`, `divabatti_*`, `arogya_*`)
- Financial calculations (`ekun_dene_rakkam`)
- Payment tracking (`payment_ss`, `payment_status`)

### Admins Table
Stores administrator credentials and configuration:
- Gram Panchayat name and contact details
- Admin authentication (email, password)
- UPI ID for payments and helpline number

### Janam Dakhla Table
Stores civil service requests for:
- Birth certificates
- Death certificates  
- Marriage certificates

## 🔄 Core Workflows

### Payment Verification Workflow
1. Citizen scans QR code and views tax details
2. Citizen makes UPI payment and uploads screenshot
3. Admin reviews screenshot in dashboard
4. Admin approves payment → status changes to "Approved"
5. System generates digital receipt 

### CSV Ingestion Process
1. Admin uploads CSV with tax records
2. System validates and normalizes financial data
3. Auto-calculates totals if not provided
4. Bulk inserts into database

### QR Code Generation
- Uses `ProcessPoolExecutor` for bulk generation
- Creates multilingual tax cards with Marathi/English text
- Generates both URL QR codes and UPI payment QR codes

## 📁 Project Structure

```
Gharpati_QrCode/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── users.db              # SQLite database (created on first run)
├── static/               # Static files (CSS, JS, user uploads)
├── templates/            # Jinja2 HTML templates
│   ├── dashboard.html    # Admin dashboard
│   ├── login.html       # Login/setup page
│   ├── view_user.html    # Citizen tax view
│   └── receipt.html     # Payment receipt template
└── sample_users.csv     # Sample CSV format for reference
```

## 📊 Key Routes

- `/login` - Admin authentication and initial setup
- `/dashboard` - Main admin interface for user management
- `/add_user_csv` - Bulk CSV upload for tax records
- `/generateqr` - QR code generation interface
- `/user/<sr_no>` - Citizen view for tax details and payment
- `/submit_payment_ss` - Payment screenshot upload
- `/approve/payment/<sr_no>` - Payment approval
- `/services` - Civil services management
- `/stats` - Payment statistics and reporting