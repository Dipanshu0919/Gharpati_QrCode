I understand - you want a README that documents the project itself without any installation or deployment steps since this is for internal use only. [1](#1-0) 

---

# Gharpati QR Code System

A specialized management platform designed for local village administrations (Gram Panchayats) to digitize property tax collection and civil service requests using QR-based automation. [1](#1-0) 

## 🎯 Purpose

The system serves two primary functions:

1. **Tax Management**: Automates the generation of QR-coded tax cards that citizens can scan to view their outstanding dues (Property Tax, Lighting, Health, etc.) and make UPI payments
2. **Civil Services**: Provides a digital interface for citizens to request official documents such as Birth Certificates, Death Certificates, and Marriage Certificates

## 👥 Target Users

- **Administrators**: Gram Panchayat officials who manage tax records via CSV uploads, approve payments, and process certificate requests
- **Citizens**: Property owners who use generated QR codes to access their personalized tax dashboards and submit payment proofs

## 🛠️ Technology Stack

- **Backend**: Flask (Python) [2](#1-1) 
- **Database**: SQLite for persistent storage of users, admins, and service requests [3](#1-2) 
- **Image Processing**: Pillow (PIL) and `qrcode` for generating multilingual tax cards and payment URIs [4](#1-3) 
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
- Payment tracking (`payment_ss`, `payment_status`) [5](#1-4) 

### Admins Table
Stores administrator credentials and configuration:
- Gram Panchayat name and contact details
- Admin authentication (email, password)
- UPI ID for payments and helpline number [6](#1-5) 

### Janam Dakhla Table
Stores civil service requests for:
- Birth certificates
- Death certificates  
- Marriage certificates [7](#1-6) 

## 🔄 Core Workflows

### Payment Verification Workflow
1. Citizen scans QR code and views tax details
2. Citizen makes UPI payment and uploads screenshot
3. Admin reviews screenshot in dashboard
4. Admin approves payment → status changes to "Approved"
5. System generates digital receipt [8](#1-7) 

### CSV Ingestion Process
1. Admin uploads CSV with tax records
2. System validates and normalizes financial data
3. Auto-calculates totals if not provided
4. Bulk inserts into database [9](#1-8) 

### QR Code Generation
- Uses `ProcessPoolExecutor` for bulk generation
- Creates multilingual tax cards with Marathi/English text
- Generates both URL QR codes and UPI payment QR codes [10](#1-9) 

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

## 🔧 Configuration

### Environment Variables
- `APP_PORT`: Port for Flask application (default: 1594) [11](#1-10) 

### Database Fields
The system uses a field dictionary for Marathi tax headers: [12](#1-11) 
- `midkatkram`: मिळकत क्र (Property Number)
- `gharpatti_*`: घरपट्टी (Property Tax)
- `divabatti_*`: दिवाबत्ती (Light Tax)
- `arogya_*`: आरोग्य (Health Tax)
- `ekun_dene_rakkam`: एकूण येणे रक्कम (Total Amount)

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

## 🛡️ Security Notes

- Session-based authentication for admin access
- File upload validation for payment screenshots
- SQL injection prevention through parameterized queries
- Input sanitization for financial calculations using Decimal type

## 📝 Development Notes

- The application uses SQLite for simplicity and portability
- Multi-language text rendering uses regex splitting for Devanagari script [13](#1-12) 
- Financial calculations use `Decimal` type for precision [14](#1-13) 
- Static file cleanup thread manages temporary uploads