# HealthBridge EMR - Setup Instructions

## Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git

## Installation Steps

### 1. Clone the Repository
```bash
git clone <your-repository-url>
cd vh
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env file with your credentials
# - Add your ICD-11 API credentials from https://icd.who.int/icdapi
# - Change SECRET_KEY to a random secure string
# - Configure other settings as needed
```

### 5. Configure the Database

The app runs on **PostgreSQL** (Neon) by default. Add your connection string to
`.env` — get it from the Neon console under *your project → Connection Details*:

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require
HB_DB_BACKEND=postgres
```

Schemas and tables are created automatically the first time the app connects,
so there is nothing else to run for a fresh install.

If you are upgrading from the old local-SQLite setup, copy the existing data
across once:

```bash
python migrate_sqlite_to_neon.py --dry-run   # preview what will be copied
python migrate_sqlite_to_neon.py             # copy the rows
```

To go back to the old files while debugging, set `HB_DB_BACKEND=sqlite`.

### 6. Run the Application
```bash
python app.py
```

The application will be available at: http://localhost:8000

## Default Accounts

### Create Your First Account
1. Go to http://localhost:8000
2. Click "Sign Up"
3. Choose account type (Doctor/Patient)
4. Complete registration

### Test Accounts (if using test data)
- **Doctor**: testdoctor2 / doctor123
- **Patient**: testpatient11 / patient123

## Features
- Multi-user authentication (Doctor, Patient, Admin roles)
- Patient management with unique Patient IDs (P0001, P0002, etc.)
- Doctor identification with unique Doctor IDs (D0001, D0002, etc.)
- Medical code search (NAMASTE + ICD-11)
- Diagnosis management with doctor-patient relationships
- FHIR R4 compliance
- Analytics and reporting
- ABHA ID integration

## Troubleshooting

### Database Issues
If `DATABASE_URL` is missing or Neon is unreachable, the app will fail on the
first query. Check that `.env` exists and that `HB_DB_BACKEND` is not set to
`sqlite`. Set `HB_DB_BACKEND=sqlite` to run against the legacy `.db` files
while you sort the connection out.

To confirm the connection from the command line:

```bash
python -c "import db; print(db.server_version())"
```

### Missing Dependencies
```bash
pip install --upgrade -r requirements.txt
```

### Port Already in Use
Change the port in app.py or use:
```bash
python app.py --port 8080
```

## Security Notes
- Change SECRET_KEY in production
- Never commit .env file to Git
- Use environment variables for sensitive data
- Enable HTTPS in production
- Regularly update dependencies

## Support
For issues and questions, please open an issue on GitHub.