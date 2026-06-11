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

### 5. Initialize Database
```bash
# The database will be created automatically on first run
# Optional: Run migration scripts if needed
python migrate_database.py
python migrate_doctor_id.py
```

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
If you encounter database errors, reset the diagnosis tables:
```bash
python reset_diagnosis_tables.py
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